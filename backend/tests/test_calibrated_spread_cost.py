"""Validation of the corrected cost basis (2026-09-05):

 * spread_estimator.build_calibrated_half_spread_frame — against SYNTHETIC
   OHLC carrying a KNOWN injected spread, before any real-data use. This
   project has shipped one formula written from memory (the discarded
   Corwin-Schultz implementation, see spread_estimator.py's header); the
   standing rule since is that a cost formula is validated against data whose
   true answer is known before it is trusted on data whose answer is not.
 * borrow_cost — the schedule's arithmetic and, more importantly, the two
   properties that make it defensible: both tails priced as hard to borrow
   (the U-shape D'Avolio and Beneish/Lee/Nichols both document), and a
   missing observation defaulting to general collateral rather than silently
   free.

WHAT THE SYNTHETIC TESTS CAN AND CANNOT SHOW. The calibrated frame's LEVEL is
pinned by construction to an externally published number, so "does it recover
the level" is not a question synthetic data can answer — the answer is "yes
by definition, at the median". What synthetic data CAN settle, and what these
tests settle, is everything else:

  1. the truncation fix (sign=True, negatives to zero) really does reduce the
     upward bias of the abs() fold at low true spreads, measured against a
     known true spread rather than against another estimate;
  2. the RANKING survives calibration — the property the whole approach rests
     on, since the level is borrowed and only the relative structure is EDGE's;
  3. the tick floor is never violated;
  4. the frame is still trailing (no look-ahead), still aligned, and still a
     drop-in for the harness's existing edge_spread cost model.
"""

import itertools

import numpy as np
import pandas as pd
import pytest
from bidask import edge_rolling

from app.services.research_lab.borrow_cost import (
    DEFAULT_SCHEDULE,
    GENERAL_COLLATERAL_BPS_PER_YEAR,
    HARD_TO_BORROW_BPS_PER_YEAR,
    BorrowSchedule,
    cross_sectional_percentiles,
    financing_bps_for_long_short_book,
)
from app.services.research_lab.cross_sectional import (
    CrossSectionalData,
    validate_cross_sectional_data,
)
from app.services.research_lab.spread_estimator import (
    COST_MODEL_WINDOW_DAYS,
    MIN_TICK_DOLLARS,
    SP500_TARGET_MEDIAN_HALF_SPREAD,
    build_calibrated_half_spread_frame,
    build_edge_half_spread_frame,
)
from tests.test_edge_cost_model import _spread_frames, _synthetic_spread_ohlc

# --- 1. the truncation fix, measured against a known true spread ------------


def test_truncation_reduces_the_averaging_bias_at_a_known_tight_spread():
    """The documented failure regime: a true FULL spread of 10bps (half-spread
    5bps), roughly where a liquid large cap lives.

    Measured on the ESTIMATOR directly rather than through the builder, so
    nothing about calibration, the tick floor, or the truncated-cell fill can
    confound it. The `bidask` docs' claim is specifically about AVERAGING —
    the abs() default "may create a small-sample bias if the estimates are
    used for averaging", which a cost model is — so the mean over all cells is
    the statistic compared, against a known truth on identical data."""
    o, h, l, c = _spread_frames({"TIGHT": 0.0010}, n_days=400)
    true_half = 0.0005
    ohlc = pd.DataFrame(
        {"open": o["TIGHT"], "high": h["TIGHT"], "low": l["TIGHT"], "close": c["TIGHT"]}
    )

    folded = (edge_rolling(ohlc, window=COST_MODEL_WINDOW_DAYS, sign=False) / 2.0).dropna()
    signed = (edge_rolling(ohlc, window=COST_MODEL_WINDOW_DAYS, sign=True) / 2.0).dropna()
    truncated = signed.clip(lower=0.0)

    assert (signed < 0).any(), (
        "no negative squared-spread estimate occurred on this fixture, so there is nothing "
        "for truncation to change — the test would be vacuous"
    )
    folded_mean = float(folded.mean())
    truncated_mean = float(truncated.mean())

    assert folded_mean > true_half, "the fold is documented to overstate; if it does not, re-derive"
    assert truncated_mean < folded_mean, (
        f"truncation ({truncated_mean:.6f}) did not reduce the fold's estimate "
        f"({folded_mean:.6f}) — the whole basis for CALIBRATED_SIGN_MODE"
    )
    assert abs(truncated_mean - true_half) < abs(folded_mean - true_half), (
        "truncation moved the estimate down but not TOWARD the truth"
    )


def test_a_truncated_cell_is_charged_the_calibrated_level_not_the_tick_floor():
    """Found on real data, where 40% of S&P 500 cells truncate: a cell whose
    squared-spread estimate came back <= 0 is a statement about the
    estimator's precision, not a claim that the stock trades for free. It gets
    the universe's calibrated central level."""
    o, h, l, c = _spread_frames({"TIGHT": 0.0010}, n_days=400)
    ohlc = pd.DataFrame(
        {"open": o["TIGHT"], "high": h["TIGHT"], "low": l["TIGHT"], "close": c["TIGHT"]}
    )
    signed = edge_rolling(ohlc, window=COST_MODEL_WINDOW_DAYS, sign=True)
    truncated_dates = signed.index[(signed <= 0.0) & signed.notna()]
    assert len(truncated_dates) > 0, "fixture produced no truncated cells; test would be vacuous"

    target = 0.0002
    frame, report = build_calibrated_half_spread_frame(
        o, h, l, c, window_days=COST_MODEL_WINDOW_DAYS, target_median_half_spread=target
    )
    assert report.n_cells_truncated_to_zero == len(truncated_dates)
    charged = frame.loc[truncated_dates, "TIGHT"]
    # The tick floor (0.005 / ~$100 = 0.5bp) is below the 2bp target here, so
    # every truncated cell must sit exactly at the target, not at the floor.
    assert np.allclose(charged.to_numpy(), target)


def test_truncation_is_recorded_not_silent():
    o, h, l, c = _spread_frames({"TIGHT": 0.0010}, n_days=400)
    _, report = build_calibrated_half_spread_frame(o, h, l, c)
    assert report.n_cells_total == o.size
    assert (
        report.n_cells_estimated
        + report.n_cells_truncated_to_zero
        + report.n_cells_no_estimate
        == report.n_cells_total
    )
    assert "scaled by" in report.summary()


# --- 2. the ranking survives calibration ------------------------------------


def test_calibration_preserves_the_cross_sectional_ranking():
    """The load-bearing property. spread_estimator's KNOWN LIMITATION block
    says EDGE "remains far more trustworthy for ranking tickers by relative
    cost" than for levels, and the calibrated builder borrows the level from
    published statistics precisely so that only the ranking has to hold. Five
    tickers with strictly ordered known true spreads must come out strictly
    ordered."""
    truths = {"T10": 0.0010, "T30": 0.0030, "T60": 0.0060, "T150": 0.0150, "T400": 0.0400}
    o, h, l, c = _spread_frames(truths, n_days=500)
    frame, _ = build_calibrated_half_spread_frame(o, h, l, c)
    medians = frame.median()
    ordered = list(truths)
    for lower, higher in itertools.pairwise(ordered):
        assert medians[lower] < medians[higher], (
            f"{lower} (true {truths[lower]}) estimated at or above {higher} "
            f"(true {truths[higher]}): {medians.to_dict()}"
        )


def test_the_calibrated_median_lands_on_the_target():
    """The level is pinned over the cells that carry a POSITIVE estimate —
    see the builder's docstring on why truncated-to-zero cells are excluded
    from the calibration but counted in the report. The scale must reproduce
    the target exactly on that set."""
    truths = {"A": 0.0010, "B": 0.0030, "C": 0.0100}
    o, h, l, c = _spread_frames(truths, n_days=400)
    frame, report = build_calibrated_half_spread_frame(
        o, h, l, c, target_median_half_spread=SP500_TARGET_MEDIAN_HALF_SPREAD
    )
    assert report.observed_median_half_spread * report.scale == pytest.approx(
        SP500_TARGET_MEDIAN_HALF_SPREAD
    )
    # And the realized median over EVERY charged cell — the number a reader
    # actually cares about — is reported separately and stays in the same
    # neighbourhood rather than drifting an order of magnitude.
    pooled = pd.Series(frame.to_numpy().ravel()).dropna()
    assert report.realized_median_half_spread == pytest.approx(float(pooled.median()))
    assert 0.2 < report.realized_median_half_spread / SP500_TARGET_MEDIAN_HALF_SPREAD < 5.0


def test_the_calibrated_frame_is_far_cheaper_than_the_uncalibrated_one_on_tight_names():
    """The whole point, stated as a number: on a universe of liquid names the
    corrected frame charges a small fraction of what the raw EDGE frame does.
    Direction and rough magnitude only — the real-data figure is in
    data/research_runs/edge_cost_correction_2026-09-05.txt."""
    truths = {"A": 0.0008, "B": 0.0012, "C": 0.0020}
    o, h, l, c = _spread_frames(truths, n_days=400)
    raw = build_edge_half_spread_frame(o, h, l, c)
    fixed, _ = build_calibrated_half_spread_frame(o, h, l, c)
    raw_median = float(pd.Series(raw.to_numpy().ravel()).dropna().median())
    fixed_median = float(pd.Series(fixed.to_numpy().ravel()).dropna().median())
    assert fixed_median < raw_median / 5.0, (raw_median, fixed_median)


# --- 3. the tick floor ------------------------------------------------------


def test_no_cell_falls_below_its_own_tick_floor():
    o, h, l, c = _spread_frames({"A": 0.0010, "B": 0.0200}, n_days=300)
    frame, report = build_calibrated_half_spread_frame(o, h, l, c)
    floor = (MIN_TICK_DOLLARS / 2.0) / c
    violations = (frame < floor - 1e-15) & frame.notna()
    assert not violations.to_numpy().any()
    assert report.n_cells_raised_to_tick_floor >= 0


def test_a_low_priced_stock_hits_the_tick_floor_far_more_often():
    """The floor is 0.005 / price, so it bites harder the cheaper the stock:
    at $100 it is 0.5bp (below any plausible charge), at $4 it is 12.5bp
    (above the 2bp target). Identical price PATHS and identical true spreads,
    rescaled — so the only thing that differs is the price level."""
    o, h, l, c = _spread_frames({"X": 0.0010}, n_days=300)
    expensive, exp_report = build_calibrated_half_spread_frame(o, h, l, c)
    cheap_frames = [f * 0.04 for f in (o, h, l, c)]  # ~$100 -> ~$4, ratios untouched
    cheap, cheap_report = build_calibrated_half_spread_frame(*cheap_frames)

    assert cheap_report.n_cells_raised_to_tick_floor > exp_report.n_cells_raised_to_tick_floor
    # The floor contract itself holds on both, exactly.
    for frame, close in ((expensive, c), (cheap, cheap_frames[3])):
        floor = (MIN_TICK_DOLLARS / 2.0) / close
        assert not (((frame < floor - 1e-15) & frame.notna()).to_numpy().any())
    # The estimator reads only intraday log RATIOS, so rescaling the price
    # level leaves the pre-floor estimate identical: every difference between
    # the two frames is the floor doing its job.
    assert cheap_report.observed_median_half_spread == pytest.approx(
        exp_report.observed_median_half_spread
    )


# --- 4. the frame is still a drop-in for the harness ------------------------


def test_calibrated_frame_is_trailing_truncation_invariant():
    """Row k must depend only on rows <= k — the property that makes reading
    the formation row look-ahead-free. NOTE the calibration scalar is pooled
    over the frame it is given, so the comparison holds the scale fixed by
    calibrating both runs to the same explicit target on the same prefix."""
    o, h, l, c = _spread_frames({"X": 0.0100}, n_days=150)
    cut = 120
    full, full_report = build_calibrated_half_spread_frame(
        o.iloc[:cut], h.iloc[:cut], l.iloc[:cut], c.iloc[:cut], window_days=63
    )
    longer, longer_report = build_calibrated_half_spread_frame(
        o, h, l, c, window_days=63, target_median_half_spread=full_report.target_median_half_spread
    )
    # Undo each run's own scale to compare the UNDERLYING estimates, which are
    # what must be trailing; the scale is a pooled statistic and is expected
    # to differ between a prefix and the whole frame.
    a = full["X"] / full_report.scale
    b = (longer["X"] / longer_report.scale).iloc[:cut]
    pd.testing.assert_series_equal(a.dropna(), b.dropna(), rtol=1e-9)


def test_calibrated_frame_is_accepted_by_the_harness_validator():
    o, h, l, c = _spread_frames({"A": 0.0010, "B": 0.0030}, n_days=200)
    frame, _ = build_calibrated_half_spread_frame(o, h, l, c)
    data = CrossSectionalData(close=c, half_spread=frame)
    validate_cross_sectional_data(data)


def test_misaligned_inputs_are_refused_loudly():
    o, h, l, c = _spread_frames({"A": 0.0010, "B": 0.0030}, n_days=100)
    with pytest.raises(ValueError, match="not aligned with open"):
        build_calibrated_half_spread_frame(o, h.iloc[:-1], l, c)


def test_a_non_positive_target_is_refused():
    o, h, l, c = _spread_frames({"A": 0.0010}, n_days=100)
    with pytest.raises(ValueError, match="must be positive"):
        build_calibrated_half_spread_frame(o, h, l, c, target_median_half_spread=0.0)


def test_calibration_start_restricts_the_pooled_median_region():
    o, h, l, c = _spread_frames({"A": 0.0010}, n_days=300)
    _, whole = build_calibrated_half_spread_frame(o, h, l, c)
    _, tail = build_calibrated_half_spread_frame(o, h, l, c, calibration_start=c.index[200])
    # Different regions, so different observed medians — the argument does
    # something. (Which is larger is data-dependent and not asserted.)
    assert whole.observed_median_half_spread != tail.observed_median_half_spread


def test_a_single_short_series_has_no_positive_cell_and_says_so():
    o, h, l, c = _synthetic_spread_ohlc(0.0010, n_days=20, seed=3)
    frames = [pd.DataFrame({"A": s}) for s in (o, h, l, c)]
    with pytest.raises(ValueError, match="nothing to pin the level to"):
        build_calibrated_half_spread_frame(*frames, window_days=63)


# --- borrow cost ------------------------------------------------------------


def test_both_tails_are_priced_hard_to_borrow():
    """The U-shape, which is the verified finding rather than the intuition:
    Beneish/Lee/Nichols p.5 report "both extremely high SIR firms and
    extremely low SIR firms have a greater probability of being on special",
    consistent with D'Avolio (2002)."""
    pct = pd.Series({"lowest": 0.02, "low_mid": 0.30, "mid": 0.50, "high_mid": 0.80, "highest": 0.97})
    rates = DEFAULT_SCHEDULE.rate_for_percentiles(pct)
    assert rates["lowest"] == HARD_TO_BORROW_BPS_PER_YEAR
    assert rates["highest"] == HARD_TO_BORROW_BPS_PER_YEAR
    assert rates["mid"] == GENERAL_COLLATERAL_BPS_PER_YEAR
    assert rates["low_mid"] == GENERAL_COLLATERAL_BPS_PER_YEAR
    assert rates["high_mid"] == GENERAL_COLLATERAL_BPS_PER_YEAR


def test_a_missing_short_interest_observation_is_general_collateral_not_free():
    rates = DEFAULT_SCHEDULE.rate_for_percentiles(pd.Series({"unknown": np.nan}))
    assert rates["unknown"] == GENERAL_COLLATERAL_BPS_PER_YEAR
    assert rates["unknown"] > 0.0, "the whole point is that nothing is charged zero"


def test_the_schedule_is_never_cheaper_than_the_zero_it_replaces():
    for pct in (0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0, np.nan):
        rate = DEFAULT_SCHEDULE.rate_for_percentiles(pd.Series([pct])).iloc[0]
        assert rate >= GENERAL_COLLATERAL_BPS_PER_YEAR > 0.0


def test_book_borrow_rate_is_the_equal_weighted_leg_average():
    # 10 names, two in the top decile of their own ranking and none at the
    # bottom by construction of the percentile helper.
    pct = pd.Series(np.linspace(0.05, 0.95, 10), index=[f"T{i}" for i in range(10)])
    expected = float(DEFAULT_SCHEDULE.rate_for_percentiles(pct).mean())
    assert DEFAULT_SCHEDULE.book_borrow_bps_per_year(pct) == pytest.approx(expected)


def test_financing_conversion_matches_the_harness_docstring():
    # cross_sectional.py: "For an equity family where only the SHORT leg pays
    # borrow at B bps/yr, pass B / 2 — half the book is short, so B/2 applied
    # to gross 2.0 is exactly B on the 1.0 short leg."
    assert financing_bps_for_long_short_book(430.0) == 215.0
    assert financing_bps_for_long_short_book(34.0) == 17.0
    with pytest.raises(ValueError, match="cannot be negative"):
        financing_bps_for_long_short_book(-1.0)


def test_percentiles_keep_missing_observations_missing():
    values = pd.Series({"a": 0.1, "b": np.nan, "c": 0.9})
    pct = cross_sectional_percentiles(values)
    assert np.isnan(pct["b"])
    assert pct["a"] < pct["c"]


def test_percentiles_of_an_all_missing_cross_section_are_all_missing():
    pct = cross_sectional_percentiles(pd.Series({"a": np.nan, "b": np.nan}))
    assert pct.isna().all()


def test_worst_case_is_the_hard_to_borrow_rate():
    assert DEFAULT_SCHEDULE.worst_case_bps_per_year() == HARD_TO_BORROW_BPS_PER_YEAR


def test_an_inverted_schedule_is_refused():
    with pytest.raises(ValueError, match="the tails cost MORE"):
        BorrowSchedule(general_collateral_bps=500.0, hard_to_borrow_bps=100.0)


def test_an_impossible_tail_fraction_is_refused():
    with pytest.raises(ValueError, match="tail_fraction"):
        BorrowSchedule(tail_fraction=0.6)


def test_percentiles_outside_the_unit_interval_are_refused():
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        DEFAULT_SCHEDULE.rate_for_percentiles(pd.Series([1.5]))
