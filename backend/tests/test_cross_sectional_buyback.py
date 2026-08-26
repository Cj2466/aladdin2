from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    run_cross_sectional_backtest,
    select_leg_tickers,
    validate_cross_sectional_data,
)
from app.services.research_lab.cross_sectional_buyback import (
    BUYBACK_COST_BPS,
    BUYBACK_FAMILY,
    BUYBACK_FINANCING_BPS_PER_YEAR,
    BUYBACK_FORMATION_START,
    BUYBACK_HOLDING_DAYS,
    BUYBACK_LOOKBACK_DAYS,
    BUYBACK_N_CORE_TRIALS,
    BUYBACK_N_ROBUSTNESS_TRIALS,
    BUYBACK_N_TRIALS,
    BUYBACK_PORTFOLIOS,
    BUYBACK_RANK_FRACTION,
    BUYBACK_ROBUSTNESS_LOOKBACK_DAYS,
    BUYBACK_WINSORIZE_QUANTILE,
    MIN_WINSORIZE_NAMES,
    SHARES_MAX_STALENESS_DAYS,
    SHARES_REPORTING_LAG_DAYS,
    BuybackScreeningSummary,
    build_buyback_disclosure,
    build_point_in_time_share_counts,
    count_split_adjustments,
    default_buyback_config,
    median_share_count_age_days,
    run_buyback_screening,
    signal_net_share_issuance,
    uninformative_window_rate,
    winsorize_cross_section,
)
from app.services.research_lab.cross_sectional_ivol import split_adjust_share_counts

# --- helpers ---------------------------------------------------------------

# The standard synthetic frame these tests measure signals on:
# bdate_range("2019-01-02", 400) runs 2019-01-02 .. 2020-07-14, so a
# 126-day signal window (127 rows) covers 2020-01-20 .. 2020-07-14.
_START = "2019-01-02"
_N = 400
# Filed before the window and visible before it starts (+45d lag ->
# 2019-09-15): this is what the window's FIRST endpoint reads.
_EARLY_FILING = "2019-08-01"
# Filed inside the window and visible inside it (+45d lag -> 2020-04-16):
# this is what the window's LAST endpoint reads.
_LATE_FILING = "2020-03-02"


def _index(n: int, start: str = _START) -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _close(tickers: list[str], n: int, start: str = _START) -> pd.DataFrame:
    idx = _index(n, start)
    rng = np.random.default_rng(11)
    return pd.DataFrame(
        {t: 100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, n))) for t in tickers}, index=idx
    )


def _shares_series(pairs: list[tuple[str, float]]) -> pd.Series:
    return pd.Series([v for _, v in pairs], index=pd.to_datetime([d for d, _ in pairs]), dtype=float)


def _step(before: float, after: float) -> pd.Series:
    """A two-filing count series whose step lands inside the standard
    126-day signal window (see _EARLY_FILING / _LATE_FILING)."""
    return _shares_series([(_EARLY_FILING, before), (_LATE_FILING, after)])


def _data_from_counts(
    counts: dict[str, pd.Series], n: int = _N, start: str = _START, splits: dict | None = None
) -> CrossSectionalData:
    close = _close(list(counts), n, start)
    frame, _ = build_point_in_time_share_counts(close, counts, splits or {})
    return CrossSectionalData(close=close, shares_outstanding=frame)


def test_the_synthetic_window_helper_really_straddles_the_filing_step():
    # Guards every signal test below: if the frame geometry drifts, the
    # helper's step would fall outside the window and the tests would pass
    # vacuously on all-NaN signals.
    idx = _index(_N)
    window_start = idx[-127]
    lag = pd.Timedelta(days=SHARES_REPORTING_LAG_DAYS)
    assert pd.Timestamp(_EARLY_FILING) + lag < window_start
    assert window_start < pd.Timestamp(_LATE_FILING) + lag < idx[-1]


# --- family shape: exactly 14, pre-declared, no drift ----------------------


def test_family_is_exactly_14_definitions_and_matches_the_declared_arithmetic():
    assert len(BUYBACK_FAMILY) == BUYBACK_N_TRIALS == 14
    assert BUYBACK_N_CORE_TRIALS == len(BUYBACK_LOOKBACK_DAYS) * len(BUYBACK_HOLDING_DAYS) * len(
        BUYBACK_PORTFOLIOS
    )
    assert BUYBACK_N_CORE_TRIALS == 12
    assert BUYBACK_N_ROBUSTNESS_TRIALS == 2
    assert BUYBACK_N_CORE_TRIALS + BUYBACK_N_ROBUSTNESS_TRIALS == BUYBACK_N_TRIALS


def test_family_size_is_the_grid_product_not_a_copied_number():
    # The literal 14 must be reachable from the declared axes, so a future
    # edit to an axis cannot leave n_trials silently stale.
    assert (
        len(BUYBACK_LOOKBACK_DAYS) * len(BUYBACK_HOLDING_DAYS) * len(BUYBACK_PORTFOLIOS)
        + len(BUYBACK_HOLDING_DAYS)
        == 14
    )


def test_family_covers_every_core_axis_combination_exactly_once():
    core = [s for s in BUYBACK_FAMILY if not s.pattern_id.endswith("_winsor")]
    assert len(core) == BUYBACK_N_CORE_TRIALS
    seen = {(s.lookback_days - 1, s.holding_days, s.portfolio) for s in core}
    expected = {
        (lb, h, p)
        for lb in BUYBACK_LOOKBACK_DAYS
        for h in BUYBACK_HOLDING_DAYS
        for p in BUYBACK_PORTFOLIOS
    }
    assert seen == expected


def test_robustness_variants_are_the_longest_lookback_long_short_only():
    robust = [s for s in BUYBACK_FAMILY if s.pattern_id.endswith("_winsor")]
    assert len(robust) == BUYBACK_N_ROBUSTNESS_TRIALS == len(BUYBACK_HOLDING_DAYS)
    assert BUYBACK_ROBUSTNESS_LOOKBACK_DAYS == max(BUYBACK_LOOKBACK_DAYS) == 504
    assert all(s.lookback_days - 1 == BUYBACK_ROBUSTNESS_LOOKBACK_DAYS for s in robust)
    assert all(s.portfolio == "long_short" for s in robust)
    assert {s.holding_days for s in robust} == set(BUYBACK_HOLDING_DAYS)


def test_family_declares_no_hold_shorter_than_a_quarter():
    # The standing lesson of this project: shorter holds lost to their longer
    # siblings because reformation cost scales with rebalance frequency, and
    # this signal only refreshes ~4x/year anyway.
    assert 21 not in BUYBACK_HOLDING_DAYS
    assert 63 not in BUYBACK_HOLDING_DAYS
    assert min(s.holding_days for s in BUYBACK_FAMILY) >= 126


def test_every_spec_requires_the_share_panel_and_is_cited():
    for spec in BUYBACK_FAMILY:
        assert spec.requires_shares_outstanding is True
        assert spec.family == "net_share_issuance"
        assert "Pontiff" in spec.citation and "2008" in spec.citation
        assert spec.rank_fraction == BUYBACK_RANK_FRACTION == 0.1
        assert spec.leg_weighting == "magnitude"
        assert spec.cohort_formation_days is None
        # This family never reads a price in its signal.
        assert not spec.requires_open
        assert not spec.requires_volume
        assert not spec.requires_market_cap
        assert not spec.requires_price_only_close


def test_family_pattern_ids_are_unique_and_do_not_collide_with_other_families():
    from app.services.research_lab.cross_sectional_bonds import BONDS_FAMILY
    from app.services.research_lab.cross_sectional_ivol import ROUND_D1_FAMILY
    from app.services.research_lab.cross_sectional_patterns import ROUND_C_FAMILY
    from app.services.research_lab.cross_sectional_patterns_d2 import D2_FAMILY
    from app.services.research_lab.cross_sectional_patterns_round_d import (
        ROUND_D_LPS_INTRADAY_FAMILY,
    )

    mine = {s.pattern_id for s in BUYBACK_FAMILY}
    assert len(mine) == len(BUYBACK_FAMILY)
    others = set()
    for family in (
        ROUND_C_FAMILY,
        ROUND_D_LPS_INTRADAY_FAMILY,
        ROUND_D1_FAMILY,
        D2_FAMILY,
        BONDS_FAMILY,
    ):
        others |= {s.pattern_id for s in family}
    assert not (mine & others)


def test_lookback_days_is_the_measurement_horizon_plus_one_row():
    # The signal differences the window's first and last row, so it needs
    # lookback + 1 rows to measure a change over `lookback` trading days.
    for spec in BUYBACK_FAMILY:
        horizon = spec.lookback_days - 1
        assert horizon in BUYBACK_LOOKBACK_DAYS


def test_default_config_is_the_shared_equity_cost_basis_and_a_fresh_object():
    a = default_buyback_config()
    b = default_buyback_config()
    assert a is not b
    assert a.cost_bps == BUYBACK_COST_BPS == 5.0
    # 0.0 is a disclosure, not an estimate -- see the module docstring.
    assert a.financing_bps_per_year == BUYBACK_FINANCING_BPS_PER_YEAR == 0.0


# --- build_point_in_time_share_counts: the step panel ----------------------


def test_panel_forward_fills_as_a_step_and_never_interpolates():
    close = _close(["A"], 300, "2020-01-01")
    counts = {"A": _shares_series([("2020-01-01", 1000.0), ("2020-06-01", 900.0)])}
    frame, missing = build_point_in_time_share_counts(close, counts, {})
    assert missing == []
    # Between the two filings (plus lag) the value is FLAT at the old count,
    # not a smooth ramp -- exactly two distinct values, never a third.
    values = frame["A"].dropna().unique()
    assert sorted(values) == [900.0, 1000.0]


def test_panel_never_back_fills_before_the_first_visible_filing():
    close = _close(["A"], 300, "2020-01-01")
    counts = {"A": _shares_series([("2020-06-01", 900.0)])}
    frame, _ = build_point_in_time_share_counts(close, counts, {})
    visible_from = pd.Timestamp("2020-06-01") + pd.Timedelta(days=SHARES_REPORTING_LAG_DAYS)
    assert frame.loc[frame.index < visible_from, "A"].isna().all()
    assert frame.loc[frame.index >= visible_from, "A"].notna().any()


def test_panel_applies_the_reporting_lag_so_a_filing_is_invisible_on_its_own_date():
    close = _close(["A"], 300, "2020-01-01")
    filed = pd.Timestamp("2020-03-02")
    counts = {"A": _shares_series([("2020-01-02", 1000.0), ("2020-03-02", 500.0)])}
    frame, _ = build_point_in_time_share_counts(close, counts, {})
    # On the filing date itself the panel still carries the OLD count.
    assert frame.loc[filed, "A"] == 1000.0
    on_or_after = frame.index[frame.index >= filed + pd.Timedelta(days=SHARES_REPORTING_LAG_DAYS)]
    assert frame.loc[on_or_after[0], "A"] == 500.0


def test_panel_refuses_a_count_carried_past_the_staleness_bound():
    close = _close(["A"], 900, "2020-01-01")
    counts = {"A": _shares_series([("2020-01-02", 1000.0)])}
    frame, _ = build_point_in_time_share_counts(close, counts, {})
    visible = pd.Timestamp("2020-01-02") + pd.Timedelta(days=SHARES_REPORTING_LAG_DAYS)
    fresh = frame.index[frame.index >= visible][0]
    assert frame.loc[fresh, "A"] == 1000.0
    dead = frame.index[frame.index > visible + pd.Timedelta(days=SHARES_MAX_STALENESS_DAYS)]
    assert len(dead) > 0
    assert frame.loc[dead, "A"].isna().all()


def test_panel_reports_tickers_with_no_usable_share_history_and_leaves_them_nan():
    close = _close(["A", "B", "C"], 200, "2020-01-01")
    counts = {
        "A": _shares_series([("2020-01-02", 1000.0)]),
        "B": pd.Series(dtype=float),
        # C's only observations are non-positive -- a data error, dropped.
        "C": _shares_series([("2020-01-02", 0.0), ("2020-02-02", -5.0)]),
    }
    frame, missing = build_point_in_time_share_counts(close, counts, {})
    assert sorted(missing) == ["B", "C"]
    assert frame["B"].isna().all()
    assert frame["C"].isna().all()
    assert frame["A"].notna().any()


def test_panel_is_aligned_with_close_exactly_so_the_harness_accepts_it():
    close = _close(["A", "B"], 200, "2020-01-01")
    counts = {"A": _shares_series([("2020-01-02", 10.0)]), "B": _shares_series([("2020-01-02", 20.0)])}
    frame, _ = build_point_in_time_share_counts(close, counts, {})
    assert frame.index.equals(close.index)
    assert frame.columns.equals(close.columns)
    validate_cross_sectional_data(CrossSectionalData(close=close, shares_outstanding=frame))


def test_panel_propagates_a_filing_that_lands_on_a_non_trading_day():
    # 2020-05-02 is a Saturday; its count must still reach the next
    # trading day once the lag has elapsed.
    close = _close(["A"], 400, "2020-01-01")
    counts = {"A": _shares_series([("2020-01-02", 1000.0), ("2020-05-02", 800.0)])}
    frame, _ = build_point_in_time_share_counts(close, counts, {})
    visible = pd.Timestamp("2020-05-02") + pd.Timedelta(days=SHARES_REPORTING_LAG_DAYS)
    after = frame.index[frame.index >= visible]
    assert frame.loc[after[0], "A"] == 800.0


def test_panel_split_adjusts_before_lagging_so_the_boundary_is_found():
    # The split correction scans a window around the EX-DATE. If the lag
    # were applied first, every observation would sit 45 days away from the
    # ex-date it is matched against.
    close = _close(["A"], 500, "2020-01-01")
    counts = {"A": _shares_series([("2020-02-03", 1_000_000.0), ("2020-07-01", 4_000_000.0)])}
    splits = {"A": pd.Series([4.0], index=pd.to_datetime(["2020-06-15"]))}
    frame, _ = build_point_in_time_share_counts(close, counts, splits)
    # Both endpoints now read the SAME post-split basis: no fake 4x step.
    assert frame["A"].dropna().nunique() == 1
    assert frame["A"].dropna().iloc[0] == pytest.approx(4_000_000.0)


# --- the signal ------------------------------------------------------------


def test_signal_is_the_negated_log_share_growth():
    data = _data_from_counts({"SHRINK": _step(1000.0, 800.0), "GROW": _step(1000.0, 1250.0)})
    signal = signal_net_share_issuance(data, lookback_days=126)
    assert signal["SHRINK"] == pytest.approx(-np.log(0.8), rel=1e-9)
    assert signal["GROW"] == pytest.approx(-np.log(1.25), rel=1e-9)
    # Buybacks rank ABOVE dilution, which is what puts them in the long leg.
    assert signal["SHRINK"] > 0 > signal["GROW"]


def test_signal_direction_puts_the_repurchaser_long_and_the_issuer_short():
    counts = {f"N{i}": _step(1000.0, 1000.0 + i + 1) for i in range(30)}
    counts["BUYER"] = _step(1000.0, 700.0)
    counts["ISSUER"] = _step(1000.0, 1400.0)
    signal = signal_net_share_issuance(_data_from_counts(counts), lookback_days=126)
    top, bottom = select_leg_tickers(signal, BUYBACK_RANK_FRACTION)
    assert "BUYER" in top
    assert "ISSUER" in bottom


def test_signal_is_symmetric_in_logs_which_is_why_logs_are_used():
    data = _data_from_counts({"HALVED": _step(1000.0, 500.0), "DOUBLED": _step(1000.0, 2000.0)})
    signal = signal_net_share_issuance(data, lookback_days=126)
    assert signal["HALVED"] == pytest.approx(-signal["DOUBLED"], rel=1e-9)


def test_signal_refuses_a_ticker_with_no_share_history():
    data = _data_from_counts({"A": _step(1000.0, 900.0), "B": pd.Series(dtype=float)})
    signal = signal_net_share_issuance(data, lookback_days=126)
    assert np.isfinite(signal["A"])
    assert np.isnan(signal["B"])


def test_signal_refuses_identical_endpoints_rather_than_reporting_a_fabricated_zero():
    # STALE: nothing was refiled inside the window, so forward-fill puts the
    # same count at both ends. A zero here would assert "issued nothing"
    # from "reported nothing". FLAT is the same shape with a real refiling
    # that happens to repeat the count -- deliberately also refused, and the
    # module docstring says why that conflation is accepted.
    counts = {
        "STALE": _shares_series([(_EARLY_FILING, 1000.0)]),
        "FLAT": _step(1000.0, 1000.0),
        "LIVE": _step(1000.0, 990.0),
    }
    signal = signal_net_share_issuance(_data_from_counts(counts), lookback_days=126)
    assert np.isnan(signal["STALE"])
    assert np.isnan(signal["FLAT"])
    assert np.isfinite(signal["LIVE"])


def test_signal_refuses_a_window_that_is_mostly_holes():
    close = _close(["A"], 900, "2019-01-02")
    # Two filings 700 days apart: the staleness bound NaNs out the middle of
    # the window, so even though a value exists at each end, coverage is
    # below MIN_SIGNAL_OBS_FRACTION.
    frame, _ = build_point_in_time_share_counts(
        close, {"A": _shares_series([("2019-06-03", 1000.0), ("2021-05-03", 900.0)])}, {}
    )
    assert frame["A"].isna().sum() > 0
    data = CrossSectionalData(close=close, shares_outstanding=frame)
    assert np.isnan(signal_net_share_issuance(data, lookback_days=252)["A"])


def test_signal_raises_loudly_when_the_share_frame_was_never_supplied():
    close = _close(["A", "B"], 200)
    with pytest.raises(ValueError, match="requires_shares_outstanding"):
        signal_net_share_issuance(CrossSectionalData(close=close), lookback_days=126)


def test_signal_returns_all_nan_on_a_window_shorter_than_the_definition():
    data = _data_from_counts({"A": _step(1000.0, 900.0)}, n=60)
    signal = signal_net_share_issuance(data, lookback_days=252)
    assert signal.isna().all()


# --- winsorization ---------------------------------------------------------


def test_the_winsorize_quantile_is_strictly_inside_the_rank_fraction():
    # THIS is what makes leg MEMBERSHIP provably invariant to winsorization:
    # the clipped tail (1%) lies strictly inside the selected leg (10%), so
    # every name clipping ties together was already in the same leg. If the
    # quantile ever exceeded the rank fraction, clipping would tie names
    # ACROSS the decile boundary and the robustness variants would silently
    # become a selection test as well as a weighting one.
    assert BUYBACK_WINSORIZE_QUANTILE < BUYBACK_RANK_FRACTION


def test_winsorize_preserves_leg_membership_because_clipping_is_monotone():
    rng = np.random.default_rng(3)
    raw = pd.Series(rng.normal(size=200), index=[f"T{i}" for i in range(200)])
    clipped = winsorize_cross_section(raw, BUYBACK_WINSORIZE_QUANTILE)
    # Membership is what actually matters, and it must be identical -- the
    # robustness variants are a WEIGHTING test, not a selection test. The
    # comparison is by SET, not by ordered list: clipping ties the tail
    # names to one another, and select_leg_tickers breaks ties
    # alphabetically, so their ORDER inside the leg can permute. Order has
    # no effect downstream -- _leg_weights reindexes by ticker and
    # _target_weights sums a dict -- but membership would.
    raw_top, raw_bottom = select_leg_tickers(raw, BUYBACK_RANK_FRACTION)
    clip_top, clip_bottom = select_leg_tickers(clipped, BUYBACK_RANK_FRACTION)
    assert set(raw_top) == set(clip_top)
    assert set(raw_bottom) == set(clip_bottom)
    # Ranks outside the clipped tails are untouched entirely.
    lo, hi = raw.quantile(BUYBACK_WINSORIZE_QUANTILE), raw.quantile(1 - BUYBACK_WINSORIZE_QUANTILE)
    interior = raw[(raw > lo) & (raw < hi)].index
    pd.testing.assert_series_equal(raw[interior], clipped[interior])


def test_winsorize_actually_compresses_the_tail_so_leg_weights_change():
    raw = pd.Series(
        list(np.linspace(-1.0, 1.0, 100)) + [50.0, -50.0],
        index=[f"T{i}" for i in range(100)] + ["HUGE", "TINY"],
    )
    clipped = winsorize_cross_section(raw, BUYBACK_WINSORIZE_QUANTILE)
    assert clipped["HUGE"] < raw["HUGE"]
    assert clipped["TINY"] > raw["TINY"]
    assert clipped.max() < 50.0


def test_winsorize_is_a_no_op_below_the_minimum_cross_section_size():
    raw = pd.Series(np.arange(float(MIN_WINSORIZE_NAMES - 1)))
    assert winsorize_cross_section(raw, 0.01).equals(raw)


def test_winsorize_leaves_nans_nan():
    raw = pd.Series([np.nan] + list(np.linspace(-1, 1, 40)), index=[f"T{i}" for i in range(41)])
    clipped = winsorize_cross_section(raw, 0.05)
    assert np.isnan(clipped["T0"])


def test_the_winsorized_spec_and_its_plain_sibling_are_genuinely_different_replays():
    rng = np.random.default_rng(7)
    counts = {}
    for i in range(80):
        drift = float(rng.normal(0.0, 0.02))
        counts[f"T{i}"] = _step(1_000_000.0, 1_000_000.0 * float(np.exp(drift)))
    # Two extreme corporate-action-shaped readings, the population the
    # robustness variant exists to probe.
    counts["MERGER"] = _step(1_000_000.0, 3_000_000.0)
    counts["MASSIVE_BUYBACK"] = _step(3_000_000.0, 1_000_000.0)
    data = _data_from_counts(counts)

    plain = signal_net_share_issuance(data, lookback_days=126)
    winsor = signal_net_share_issuance(data, lookback_days=126, winsorize_quantile=0.01)
    # Same legs (by membership -- see the tie note above)...
    for a, b in zip(select_leg_tickers(plain, 0.1), select_leg_tickers(winsor, 0.1), strict=True):
        assert set(a) == set(b)
    # ...different magnitudes, hence different leg WEIGHTS, hence a
    # different return stream. That is the whole content of the variant.
    assert not np.allclose(plain.dropna().to_numpy(), winsor.dropna().to_numpy())


# --- THE REAL GE / ANET SPLIT-CONTAMINATION REGRESSION ---------------------
#
# Real values read off live yfinance on 2026-08-27 and frozen here, so these
# assert against genuine market data with no network dependence in the test
# suite. Sources: YFinanceProvider.get_shares_outstanding (raw as-filed
# counts) and .get_market_cap_basis (dated split ratios).

# GE: 1-for-8 REVERSE split, ex-date 2021-08-02 (yfinance ratio 0.125). The
# raw count drops 8.00x across it. GE's other three "splits" are Yahoo's
# PRICE adjustments for the Wabtec (2019), GE HealthCare (2023) and GE
# Vernova (2024) spin-offs -- the share count does NOT jump by those ratios
# and no adjustment must be applied for them.
_GE_SPLITS = pd.Series(
    [1.04, 0.125, 1.281, 1.253],
    index=pd.to_datetime(["2019-02-26", "2021-08-02", "2023-01-04", "2024-04-02"]),
)
_GE_SHARES = _shares_series(
    [
        ("2020-11-26", 8_759_870_464.0),
        ("2021-02-13", 8_767_939_584.0),
        ("2021-02-15", 8_767_939_584.0),
        ("2021-03-17", 8_767_939_584.0),
        ("2021-03-24", 8_784_650_240.0),
        ("2021-04-23", 8_745_350_144.0),
        ("2021-04-24", 8_654_990_336.0),
        ("2021-04-28", 8_778_640_384.0),
        ("2021-06-05", 8_860_390_400.0),
        ("2021-06-06", 8_778_640_384.0),
        ("2021-06-09", 8_784_959_488.0),
        ("2021-06-10", 8_778_640_384.0),
        ("2021-07-13", 8_778_640_384.0),
        ("2021-07-15", 8_778_640_384.0),
        ("2021-07-28", 8_781_299_712.0),
        ("2021-08-02", 1_097_660_032.0),
        ("2021-08-19", 1_097_660_032.0),
        ("2021-08-31", 1_107_049_984.0),
        ("2021-09-01", 1_097_660_032.0),
        ("2021-10-27", 1_098_140_032.0),
        ("2021-11-05", 1_106_070_016.0),
        ("2021-11-06", 1_098_140_032.0),
        ("2021-11-16", 1_098_140_032.0),
        ("2022-02-12", 1_099_320_064.0),
        ("2022-02-15", 1_099_320_064.0),
    ]
)

# ANET: 4-for-1 FORWARD split, ex-date 2021-11-18. yfinance's count switches
# five days LATE, on 2021-11-23, by 3.93x.
_ANET_SPLITS = pd.Series([4.0, 4.0], index=pd.to_datetime(["2021-11-18", "2024-12-04"]))
_ANET_SHARES = _shares_series(
    [
        ("2020-11-26", 75_661_504.0),
        ("2021-01-28", 75_661_504.0),
        ("2021-02-03", 75_606_496.0),
        ("2021-02-20", 76_331_600.0),
        ("2021-02-22", 76_331_600.0),
        ("2021-03-17", 76_331_600.0),
        ("2021-03-30", 77_219_696.0),
        ("2021-04-01", 75_565_400.0),
        ("2021-04-07", 77_261_296.0),
        ("2021-04-08", 76_331_600.0),
        ("2021-04-23", 77_207_504.0),
        ("2021-04-24", 75_799_800.0),
        ("2021-04-27", 76_271_400.0),
        ("2021-05-08", 76_321_800.0),
        ("2021-05-10", 76_321_800.0),
        ("2021-06-26", 76_591_504.0),
        ("2021-06-28", 76_321_800.0),
        ("2021-07-31", 76_446_200.0),
        ("2021-08-01", 76_321_800.0),
        ("2021-08-04", 76_716_600.0),
        ("2021-08-26", 76_716_600.0),
        ("2021-09-15", 76_832_400.0),
        ("2021-09-16", 76_716_600.0),
        ("2021-09-18", 76_716_600.0),
        ("2021-09-22", 76_716_600.0),
        ("2021-09-28", 77_439_104.0),
        ("2021-09-29", 76_716_600.0),
        ("2021-11-04", 76_820_896.0),
        ("2021-11-11", 78_174_400.0),
        ("2021-11-23", 307_300_000.0),
    ]
)


def _real_split_cross_section() -> tuple[pd.DataFrame, dict, dict]:
    """GE and ANET's real series dropped into a plausible 62-name S&P-scale
    cross-section of ordinary issuers, so decile membership is a meaningful
    question rather than a two-name comparison."""
    rng = np.random.default_rng(2026)
    counts: dict[str, pd.Series] = {"GE": _GE_SHARES, "ANET": _ANET_SHARES}
    for i in range(60):
        # Ordinary firms: between -4% and +4% share growth over the window,
        # filed quarterly. Nothing here comes close to a split-sized move.
        growth = float(np.linspace(-0.04, 0.04, 60)[i])
        base = 1.0e9 * (1.0 + 0.1 * rng.random())
        counts[f"N{i:02d}"] = _shares_series(
            [
                ("2020-11-26", base),
                ("2021-03-01", base * (1 + growth * 0.3)),
                ("2021-06-01", base * (1 + growth * 0.6)),
                ("2021-09-01", base * (1 + growth * 0.8)),
                ("2021-12-01", base * (1 + growth)),
                ("2022-02-14", base * (1 + growth)),
            ]
        )
    close = _close(list(counts), 370, "2020-11-02")
    splits = {"GE": _GE_SPLITS, "ANET": _ANET_SPLITS}
    return close, counts, splits


def test_real_ge_reverse_split_lands_in_the_long_decile_uncorrected_and_nowhere_corrected():
    close, counts, splits = _real_split_cross_section()
    corrected, _ = build_point_in_time_share_counts(close, counts, splits)
    uncorrected, _ = build_point_in_time_share_counts(close, counts, {})

    bad = signal_net_share_issuance(
        CrossSectionalData(close=close, shares_outstanding=uncorrected), lookback_days=252
    )
    good = signal_net_share_issuance(
        CrossSectionalData(close=close, shares_outstanding=corrected), lookback_days=252
    )

    bad_top, _ = select_leg_tickers(bad, BUYBACK_RANK_FRACTION)
    good_top, good_bottom = select_leg_tickers(good, BUYBACK_RANK_FRACTION)

    # UNCORRECTED: GE reads as an ~87.5% share reduction -- log(8) = 2.08 --
    # the single most extreme "buyback" in the cross-section, maximum long
    # weight. It bought back nothing of the kind.
    assert bad["GE"] == pytest.approx(np.log(8.0), rel=0.01)
    assert bad["GE"] == bad.max()
    assert "GE" in bad_top

    # CORRECTED: GE's real one-year share change is a fraction of a percent
    # and it is nowhere near either leg.
    assert abs(good["GE"]) < 0.01
    assert "GE" not in good_top
    assert "GE" not in good_bottom


def test_real_anet_forward_split_lands_in_the_short_decile_uncorrected_and_nowhere_corrected():
    close, counts, splits = _real_split_cross_section()
    corrected, _ = build_point_in_time_share_counts(close, counts, splits)
    uncorrected, _ = build_point_in_time_share_counts(close, counts, {})

    bad = signal_net_share_issuance(
        CrossSectionalData(close=close, shares_outstanding=uncorrected), lookback_days=252
    )
    good = signal_net_share_issuance(
        CrossSectionalData(close=close, shares_outstanding=corrected), lookback_days=252
    )
    _, bad_bottom = select_leg_tickers(bad, BUYBACK_RANK_FRACTION)
    good_top, good_bottom = select_leg_tickers(good, BUYBACK_RANK_FRACTION)

    # UNCORRECTED: ANET reads as ~300% dilution -- -log(4) = -1.39 -- the
    # most extreme "issuer" in the cross-section, maximum short weight.
    assert bad["ANET"] == pytest.approx(-np.log(4.0), rel=0.02)
    assert bad["ANET"] == bad.min()
    assert "ANET" in bad_bottom

    # CORRECTED: ANET's real one-year change is well under a percent.
    assert abs(good["ANET"]) < 0.02
    assert "ANET" not in good_top
    assert "ANET" not in good_bottom


def test_the_split_correction_is_what_moves_them_not_some_other_difference():
    # The two panels must be IDENTICAL for every ordinary name -- otherwise
    # the two tests above would prove nothing about splits specifically.
    close, counts, splits = _real_split_cross_section()
    corrected, _ = build_point_in_time_share_counts(close, counts, splits)
    uncorrected, _ = build_point_in_time_share_counts(close, counts, {})
    ordinary = [c for c in corrected.columns if c not in ("GE", "ANET")]
    pd.testing.assert_frame_equal(corrected[ordinary], uncorrected[ordinary])
    assert not corrected["GE"].equals(uncorrected["GE"])
    assert not corrected["ANET"].equals(uncorrected["ANET"])


def test_real_ge_series_is_continuous_across_its_reverse_split_after_correction():
    adjusted = split_adjust_share_counts(_GE_SHARES, _GE_SPLITS)
    # 2021-07-28 -> 2021-08-02 is the raw 8x cliff. After correction the two
    # observations agree to better than 0.01%, which is what "a split creates
    # no shares" means operationally.
    step = adjusted.loc["2021-08-02"] / adjusted.loc["2021-07-28"]
    assert step == pytest.approx(1.0, abs=1e-4)
    raw_step = _GE_SHARES.loc["2021-08-02"] / _GE_SHARES.loc["2021-07-28"]
    assert raw_step == pytest.approx(0.125, rel=1e-3)
    # No consecutive step anywhere in the corrected series is split-sized.
    ratios = (adjusted / adjusted.shift(1)).dropna()
    assert ratios.min() > 0.5
    assert ratios.max() < 2.0


def test_the_spin_off_ratios_yahoo_records_as_splits_are_correctly_left_alone():
    # GE's 1.04 / 1.281 / 1.253 entries are price adjustments for the
    # Wabtec, GE HealthCare and GE Vernova separations. The share count does
    # not move by those ratios, so no jump is found and no adjustment is
    # applied -- if one were, it would manufacture a 25-28% fake "issuance"
    # step in exactly the years those spin-offs happened.
    spin_offs_only = _GE_SPLITS.drop(pd.Timestamp("2021-08-02"))
    assert split_adjust_share_counts(_GE_SHARES, spin_offs_only).equals(_GE_SHARES)


def test_anet_boundary_is_taken_from_the_series_own_late_jump_not_the_ex_date():
    adjusted = split_adjust_share_counts(_ANET_SHARES, _ANET_SPLITS)
    # The ex-date is 2021-11-18 but the count switches on 2021-11-23. Keying
    # off the ex-date would leave 2021-11-23's already-post-split count
    # multiplied by 4 as well.
    assert adjusted.loc["2021-11-23"] == pytest.approx(307_300_000.0)
    assert adjusted.loc["2021-11-11"] == pytest.approx(78_174_400.0 * 4.0)
    step = adjusted.loc["2021-11-23"] / adjusted.loc["2021-11-11"]
    assert step == pytest.approx(0.983, rel=0.01)


def test_count_split_adjustments_measures_what_the_correction_actually_did():
    n_tickers, n_obs = count_split_adjustments(
        {"GE": _GE_SHARES, "ANET": _ANET_SHARES, "NOSPLIT": _shares_series([("2021-01-04", 1.0)])},
        {"GE": _GE_SPLITS, "ANET": _ANET_SPLITS},
    )
    assert n_tickers == 2  # NOSPLIT carries no splits at all
    # GE: the 15 observations before 2021-08-02. ANET: the 29 before
    # 2021-11-23.
    assert n_obs == 15 + 29


# --- harness integration ---------------------------------------------------


def test_a_spec_requiring_the_share_panel_fails_loudly_when_it_is_absent():
    close = _close(["A", "B", "C"], 300, "2019-01-02")
    spec = BUYBACK_FAMILY[0]
    with pytest.raises(ValueError, match="requires point-in-time share counts"):
        run_cross_sectional_backtest(
            CrossSectionalData(close=close), spec, CrossSectionalConfig(), lambda t, d: True
        )


def test_a_misaligned_share_frame_is_rejected_by_the_harness_validator():
    close = _close(["A", "B"], 100, "2019-01-02")
    bad = pd.DataFrame({"A": [1.0] * 100}, index=close.index)
    with pytest.raises(ValueError, match="shares_outstanding is not aligned"):
        validate_cross_sectional_data(CrossSectionalData(close=close, shares_outstanding=bad))


def test_the_share_panel_is_sliced_to_the_formation_date_so_look_ahead_is_impossible():
    close = _close([f"T{i}" for i in range(20)], 400, "2019-01-02")
    frame = pd.DataFrame(1000.0, index=close.index, columns=close.columns)
    seen: list[pd.Timestamp] = []

    def spy(history: CrossSectionalData) -> pd.Series:
        assert history.shares_outstanding is not None
        seen.append(history.shares_outstanding.index[-1])
        # A future row must be structurally unreachable, not merely unread.
        assert history.shares_outstanding.index.max() == history.close.index.max()
        return pd.Series(np.arange(float(len(history.close.columns))), index=history.close.columns)

    spec = CrossSectionalSpec(
        pattern_id="spy",
        family="t",
        citation="t",
        signal_fn=spy,
        lookback_days=60,
        holding_days=126,
        portfolio="long_short",
        rank_fraction=0.2,
        requires_shares_outstanding=True,
    )
    result = run_cross_sectional_backtest(
        CrossSectionalData(close=close, shares_outstanding=frame),
        spec,
        CrossSectionalConfig(min_names_per_leg=2),
        lambda t, d: True,
    )
    assert result.status == "ok"
    assert seen
    formation_dates = [f.date for f in result.formations]
    assert seen == formation_dates


def test_existing_families_are_unaffected_by_the_new_optional_frame():
    # A spec that never declares requires_shares_outstanding must replay
    # byte-identically whether or not the frame is present.
    close = _close([f"T{i}" for i in range(20)], 400, "2019-01-02")
    frame = pd.DataFrame(1000.0, index=close.index, columns=close.columns)

    def constant_rank(history: CrossSectionalData) -> pd.Series:
        return pd.Series(np.arange(float(len(history.close.columns))), index=history.close.columns)

    spec = CrossSectionalSpec(
        pattern_id="legacy",
        family="t",
        citation="t",
        signal_fn=constant_rank,
        lookback_days=60,
        holding_days=126,
        portfolio="long_short",
        rank_fraction=0.2,
    )
    config = CrossSectionalConfig(min_names_per_leg=2)
    without = run_cross_sectional_backtest(
        CrossSectionalData(close=close), spec, config, lambda t, d: True
    )
    with_frame = run_cross_sectional_backtest(
        CrossSectionalData(close=close, shares_outstanding=frame), spec, config, lambda t, d: True
    )
    pd.testing.assert_series_equal(without.daily_returns, with_frame.daily_returns)
    assert without.total_cost == with_frame.total_cost


def test_a_longer_hold_reforms_less_often_and_pays_less_turnover_cost():
    # The family's whole holding-period argument, tested rather than argued.
    rng = np.random.default_rng(5)
    tickers = [f"T{i}" for i in range(60)]
    counts = {}
    for t in tickers:
        base = 1.0e9
        pairs = [("2016-01-04", base)]
        for k, d in enumerate(("2017-01-04", "2018-01-04", "2019-01-04", "2020-01-06")):
            base *= float(np.exp(rng.normal(0.0, 0.05)))
            pairs.append((d, base))
        counts[t] = _shares_series(pairs)
    close = _close(tickers, 1000, "2017-01-02")
    frame, _ = build_point_in_time_share_counts(close, counts, {})
    data = CrossSectionalData(close=close, shares_outstanding=frame)

    config = default_buyback_config()
    short = next(s for s in BUYBACK_FAMILY if s.pattern_id == "nsi_l126_ls_h126")
    long_ = next(s for s in BUYBACK_FAMILY if s.pattern_id == "nsi_l126_ls_h252")
    r_short = run_cross_sectional_backtest(data, short, config, lambda t, d: True)
    r_long = run_cross_sectional_backtest(data, long_, config, lambda t, d: True)
    assert len(r_short.formations) > len(r_long.formations)
    assert r_short.total_cost > r_long.total_cost


# --- diagnostics -----------------------------------------------------------


def test_median_share_count_age_is_small_for_a_densely_filed_panel():
    close = _close(["A"], 300, "2020-01-01")
    dates = pd.bdate_range("2019-10-01", periods=200, freq="7D")
    counts = {"A": pd.Series(np.linspace(1000.0, 900.0, len(dates)), index=dates)}
    frame, _ = build_point_in_time_share_counts(close, counts, {})
    age = median_share_count_age_days(frame, counts)
    assert 0.0 <= age <= 20.0


def test_median_share_count_age_is_large_for_a_sparsely_filed_panel():
    close = _close(["A"], 300, "2020-01-01")
    counts = {"A": _shares_series([("2019-06-03", 1000.0), ("2019-12-02", 950.0)])}
    frame, _ = build_point_in_time_share_counts(close, counts, {})
    assert median_share_count_age_days(frame, counts) > 100.0


def test_median_share_count_age_is_nan_when_nothing_resolved():
    close = _close(["A"], 50, "2020-01-01")
    frame = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    assert np.isnan(median_share_count_age_days(frame, {}))


def test_median_share_count_age_can_be_scoped_to_the_replayed_sample():
    # The warmup padding is the sparsest stretch of the real data, so the
    # whole-panel figure describes a period no formation ever ranked.
    close = _close(["A"], 700, "2020-01-01")
    counts = {"A": _shares_series([("2019-06-03", 1000.0)])}
    dense = pd.bdate_range("2021-06-01", periods=60, freq="5D")
    counts["A"] = pd.concat([counts["A"], pd.Series(np.linspace(999.0, 950.0, 60), index=dense)])
    whole = median_share_count_age_days(frame_a := build_point_in_time_share_counts(close, counts, {})[0], counts)
    scoped = median_share_count_age_days(frame_a, counts, since=date(2021, 8, 1))
    assert scoped < whole


def test_uninformative_window_rate_is_one_when_nothing_was_ever_refiled():
    close = _close(["A"], 400, "2020-01-01")
    frame, _ = build_point_in_time_share_counts(
        close, {"A": _shares_series([("2019-06-03", 1000.0)])}, {}
    )
    assert uninformative_window_rate(frame, 126) == pytest.approx(1.0)


def test_uninformative_window_rate_is_zero_for_a_continuously_refiled_panel():
    close = _close(["A"], 400, "2020-01-01")
    dates = pd.bdate_range("2019-06-03", periods=300, freq="5D")
    counts = {"A": pd.Series(np.linspace(1000.0, 900.0, len(dates)), index=dates)}
    frame, _ = build_point_in_time_share_counts(close, counts, {})
    assert uninformative_window_rate(frame, 126) == pytest.approx(0.0)


def test_uninformative_window_rate_is_nan_on_an_unusable_panel():
    close = _close(["A"], 400, "2020-01-01")
    frame = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    assert np.isnan(uninformative_window_rate(frame, 126))


# --- production entry point (offline) --------------------------------------


# Real S&P 500 members throughout 2018-2025, verified against
# sp500_membership_history.was_member. The entry point uses the REAL
# point-in-time membership gate (this is an equity family), so a synthetic
# ticker like "T001" would be rejected on every formation date and the run
# would fail with EmptyEligibleUniverseError. Same reasoning, and the same
# device, as test_cross_sectional_ivol's _STALWART_MEMBERS.
_STALWART_MEMBERS = [
    "A", "AAPL", "ABBV", "ABT", "ACN", "ADBE", "ADI", "ADM", "ADP", "ADSK",
    "AEE", "AEP", "AES", "AFL", "AIG", "AIZ", "AJG", "AKAM", "ALB", "ALGN",
    "ALL", "ALLE", "AMAT", "AMD", "AME", "AMGN", "AMP", "AMT", "AMZN", "AON",
    "AOS", "APA", "APD", "APH", "APTV", "ARE", "AVB", "AVGO", "AVY", "AWK",
    "AXP", "AZO", "BA", "BAC", "BAX", "BBY", "BDX", "BEN", "BIIB", "BK",
    "BKNG", "BKR", "BLK", "BMY", "BSX", "BXP", "C", "CAG", "CAH", "CAT",
]


class _FakeProvider:
    """Stands in for YFinanceProvider with no network. Records what it was
    asked for, so the entry point's fetch discipline (padding, priced-only
    share fetch) is itself under test. Serves prices only for `tickers`, so
    everything else in the real point-in-time universe lands in
    missing_price_data exactly as an index leaver would."""

    def __init__(self, tickers: list[str], seed: int = 41):
        self.tickers = list(tickers)
        self.calls: dict[str, tuple] = {}
        self.seed = seed

    def _frame(self, tickers, start, end):
        served = [t for t in tickers if t in self.tickers]
        index = pd.bdate_range(start, end)
        rng = np.random.default_rng(self.seed)
        close = pd.DataFrame(
            {t: 100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.012, len(index)))) for t in served},
            index=index,
        )
        return close, [t for t in tickers if t not in served]

    def get_price_history(self, tickers, start, end):
        self.calls["price"] = (list(tickers), start, end)
        return self._frame(tickers, start, end)

    def get_market_cap_basis(self, tickers, start, end):
        self.calls["basis"] = (list(tickers), start, end)
        close, missing = self._frame(tickers, start, end)
        return close, {}, missing

    def get_shares_outstanding(self, tickers, start, end):
        self.calls["shares"] = (list(tickers), start, end)
        rng = np.random.default_rng(self.seed + 1)
        filings = pd.date_range(start, end, freq="91D")
        shares = {}
        for t in tickers:
            if t not in self.tickers:
                continue
            shares[t] = pd.Series(
                1.0e9 * np.exp(np.cumsum(rng.normal(0.0, 0.02, len(filings)))), index=filings
            )
        return shares, [t for t in tickers if t not in shares]


def test_screening_rejects_a_start_before_point_in_time_membership_coverage():
    with pytest.raises(ValueError, match="predates point-in-time membership"):
        run_buyback_screening(start=date(2010, 1, 4), end=date(2020, 1, 1))


def test_screening_runs_end_to_end_offline_and_reports_every_disclosure():
    provider = _FakeProvider(_STALWART_MEMBERS)
    summary = run_buyback_screening(
        start=date(2018, 1, 2), end=date(2025, 6, 30), provider=provider
    )

    assert isinstance(summary, BuybackScreeningSummary)
    assert summary.n_trials == 14
    assert summary.universe_size > 500  # the REAL point-in-time universe
    assert summary.formation_start == date(2018, 1, 2)
    assert summary.panel_start is not None and summary.panel_end is not None
    assert set(summary.uninformative_window_rate) == set(BUYBACK_LOOKBACK_DAYS)
    assert summary.results, "the fake panel is long enough that specs should replay"
    for r in summary.results:
        assert r.deflated_sharpe.n_trials == 14  # every definition counted
        assert r.n_formations > 0
        assert np.isfinite(r.sharpe_annualized)
    sharpes = [r.sharpe_annualized for r in summary.results]
    assert sharpes == sorted(sharpes, reverse=True)
    assert "Pre-declared family size 14" in summary.disclosure
    assert "GE" in summary.disclosure and "ANET" in summary.disclosure
    assert "DISCLOSURE, not" in summary.disclosure
    assert summary.turnover_per_formation


def test_screening_pads_price_history_and_fetches_shares_only_for_priced_tickers():
    provider = _FakeProvider(_STALWART_MEMBERS)
    summary = run_buyback_screening(
        start=date(2018, 1, 2), end=date(2024, 1, 1), provider=provider
    )
    price_tickers, price_start, _ = provider.calls["price"]
    assert len(price_tickers) > 500
    assert price_start < date(2018, 1, 2)
    # Only priced tickers cost a per-ticker share-count network call.
    shares_tickers, _, _ = provider.calls["shares"]
    assert set(shares_tickers) == set(_STALWART_MEMBERS)
    assert set(summary.missing_price_data) == set(price_tickers) - set(_STALWART_MEMBERS)
    assert any("resolved no price data" in w for w in summary.warnings)


def test_screening_asks_for_the_market_cap_basis_only_to_get_split_ratios():
    # The close frame from that call is deliberately discarded: this family
    # never multiplies a share count by a price. Prove it by serving a
    # wildly wrong one and checking nothing moves.
    baseline = run_buyback_screening(
        start=date(2018, 1, 2), end=date(2024, 1, 1), provider=_FakeProvider(_STALWART_MEMBERS)
    )

    provider = _FakeProvider(_STALWART_MEMBERS)
    real = provider.get_market_cap_basis
    calls = {"n": 0}

    def wrong_price(t, s, e):
        calls["n"] += 1
        close, splits, missing = real(t, s, e)
        return close * 1e6, splits, missing

    provider.get_market_cap_basis = wrong_price
    corrupted = run_buyback_screening(
        start=date(2018, 1, 2), end=date(2024, 1, 1), provider=provider
    )
    assert calls["n"] == 1
    assert [r.pattern_id for r in baseline.results] == [r.pattern_id for r in corrupted.results]
    assert [r.sharpe_annualized for r in baseline.results] == [
        r.sharpe_annualized for r in corrupted.results
    ]


def test_screening_returns_an_honest_empty_summary_when_no_price_data_resolves():
    class _Empty:
        def get_price_history(self, tickers, start, end):
            return pd.DataFrame(), list(tickers)

    summary = run_buyback_screening(
        start=date(2018, 1, 2), end=date(2024, 1, 1), provider=_Empty()
    )
    assert summary.results == []
    assert summary.n_trials == 14
    assert summary.warnings
    assert "nothing was screened" in summary.warnings[0]


def test_screening_respects_a_caller_supplied_config():
    provider = _FakeProvider(_STALWART_MEMBERS)
    config = CrossSectionalConfig(cost_bps=25.0, financing_bps_per_year=17.0)
    summary = run_buyback_screening(
        start=date(2018, 1, 2), end=date(2024, 1, 1), provider=provider, config=config
    )
    assert summary.cost_bps == 25.0
    assert summary.financing_bps_per_year == 17.0
    assert config.formation_start == date(2018, 1, 2)
    assert "25.0bp one-way" in summary.disclosure


def test_the_stalwart_members_really_are_point_in_time_members():
    # Guards the offline tests above: if any of these stopped being a member
    # over the window, those runs would quietly rank a thinner cross-section.
    from app.services.research_lab.sp500_membership_history import was_member

    for probe in (date(2018, 1, 2), date(2021, 6, 1), date(2024, 6, 3)):
        members = [t for t in _STALWART_MEMBERS if was_member(t, probe)]
        assert len(members) >= 55, (probe, set(_STALWART_MEMBERS) - set(members))


def test_screening_reports_a_breakeven_borrow_for_every_replayed_spec():
    # Financing is modeled at ZERO, so this is the number that decides
    # whether any positive Sharpe here would survive a real short book.
    provider = _FakeProvider(_STALWART_MEMBERS)
    summary = run_buyback_screening(
        start=date(2018, 1, 2), end=date(2025, 6, 30), provider=provider
    )
    replayed = {r.pattern_id for r in summary.results}
    assert set(summary.breakeven_short_borrow_bps_per_year) == replayed
    for r in summary.results:
        borrow = summary.breakeven_short_borrow_bps_per_year[r.pattern_id]
        assert np.isfinite(borrow)
        # A losing spec must report a NEGATIVE breakeven, not be omitted --
        # otherwise the field would look like something only winners have.
        assert (borrow > 0) == (r.sharpe_annualized > 0)
    assert "BREAKEVEN COSTS" in summary.disclosure
    assert "bp/yr" in summary.disclosure


def test_breakeven_trade_cost_exceeds_the_assumed_cost_for_a_profitable_spec():
    provider = _FakeProvider(_STALWART_MEMBERS)
    summary = run_buyback_screening(
        start=date(2018, 1, 2), end=date(2025, 6, 30), provider=provider
    )
    for pattern_id, breakeven in summary.breakeven_cost_bps.items():
        # It is only computed for a spec whose GROSS edge is positive, and
        # for such a spec the breakeven must sit above the cost that was
        # actually charged -- otherwise the charge already consumed it.
        assert breakeven > 0.0
        assert pattern_id in {r.pattern_id for r in summary.results}


def test_disclosure_reports_measured_turnover_per_spec_not_an_assumption():
    summary = BuybackScreeningSummary(
        results=[],
        n_trials=14,
        universe_size=1,
        missing_price_data=[],
        tickers_without_share_history=[],
        panel_start=date(2018, 1, 2),
        panel_end=date(2026, 1, 2),
        formation_start=date(2018, 1, 2),
        n_tickers_with_splits=3,
        n_split_adjusted_observations=44,
        median_signal_endpoint_age_days=37.0,
        uninformative_window_rate={126: 0.08, 252: 0.02, 504: 0.002},
        turnover_per_formation={"nsi_l126_ls_h126": 1.5, "nsi_l126_ls_h252": 1.5},
        breakeven_cost_bps={"nsi_l126_ls_h126": 12.5},
        breakeven_short_borrow_bps_per_year={"nsi_l126_ls_h126": 63.0, "nsi_l126_ls_h252": -8.0},
    )
    text = build_buyback_disclosure(summary, default_buyback_config())
    assert "mean turnover 1.500" in text
    assert "2.0 reformations/yr" in text  # 252/126
    assert "1.0 reformations/yr" in text  # 252/252
    # The shorter hold must come out MORE expensive per year on IDENTICAL
    # turnover -- the family's whole holding-period argument, in the output.
    assert "-> 15.0bp/yr" in text  # 1.5 * 5bp * 2 reformations
    assert "-> 7.5bp/yr" in text  # 1.5 * 5bp * 1 reformation
    assert "126d lookback 8.0%" in text
    assert "borrow 63bp/yr, trade 12.5bp one-way" in text
    # A losing spec's negative breakeven is shown, not suppressed.
    assert "borrow -8bp/yr, trade n/a" in text


def test_screening_warns_loudly_if_the_split_correction_did_nothing():
    provider = _FakeProvider(_STALWART_MEMBERS)
    real = provider.get_market_cap_basis

    def with_undetectable_splits(t, s, e):
        close, _, missing = real(t, s, e)
        # A split ratio that leaves no matching jump anywhere in the share
        # series -- which is what a silently broken correction also looks
        # like, and the consequence of that is GE in the long decile.
        return (
            close,
            {tk: pd.Series([2.0], index=pd.to_datetime(["2020-06-01"])) for tk in close.columns},
            missing,
        )

    provider.get_market_cap_basis = with_undetectable_splits
    summary = run_buyback_screening(
        start=date(2018, 1, 2), end=date(2024, 1, 1), provider=provider
    )
    assert summary.n_tickers_with_splits == len(_STALWART_MEMBERS)
    assert summary.n_split_adjusted_observations == 0
    assert any("changed ZERO observations" in w for w in summary.warnings)


def test_the_declared_formation_start_is_the_documented_one():
    assert BUYBACK_FORMATION_START == date(2018, 1, 2)
