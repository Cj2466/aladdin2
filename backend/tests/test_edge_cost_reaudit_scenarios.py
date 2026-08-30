"""Tests for edge_cost_reaudit_scenarios — the cost-input builders for the
2026-08-30 corrected-cost re-audit. Everything is checked against hand-
computed ground truth on tiny synthetic fixtures, matching this project's
test convention: no fixture value is produced by the code under test."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.edge_cost_reaudit_scenarios import (
    scale_half_spread_frame_to_median,
    tick_floor_half_spread_bps,
    tiered_cost_bps_by_ticker,
)

# --- tick_floor_half_spread_bps ----------------------------------------


def test_tick_floor_exact_arithmetic():
    # full spread >= $0.01 -> one-way half-spread >= 0.005/price.
    # $100 stock: 0.005/100 = 5e-5 = 0.5bp. $12.50 stock: 0.005/12.5 = 4bp.
    assert tick_floor_half_spread_bps(100.0) == pytest.approx(0.5)
    assert tick_floor_half_spread_bps(12.5) == pytest.approx(4.0)
    assert tick_floor_half_spread_bps(50.0) == pytest.approx(1.0)


def test_tick_floor_rejects_non_positive_price():
    with pytest.raises(ValueError, match="positive price"):
        tick_floor_half_spread_bps(0.0)
    with pytest.raises(ValueError, match="positive price"):
        tick_floor_half_spread_bps(-3.0)


# --- tiered_cost_bps_by_ticker -----------------------------------------

LARGE = ["BIGCO", "HUGEco"]
MID_SMALL = ["TINY", "CHEAP"]
# BIGCO $200 -> floor 0.25bp; HUGEco $40 -> floor 1.25bp;
# TINY $80 -> floor 0.625bp; CHEAP $10 -> floor 5bp.
MEDIAN_CLOSES = {"BIGCO": 200.0, "HUGEco": 40.0, "TINY": 80.0, "CHEAP": 10.0}


def test_tier_rates_assigned_and_floored():
    costs = tiered_cost_bps_by_ticker(
        ["BIGCO", "HUGEco", "TINY", "CHEAP"],
        LARGE,
        MID_SMALL,
        large_cap_rate_bps=1.0,
        mid_small_rate_bps=4.0,
        median_close_by_ticker=MEDIAN_CLOSES,
    )
    assert costs["BIGCO"] == pytest.approx(1.0)  # floor 0.25 < rate 1.0
    assert costs["HUGEco"] == pytest.approx(1.25)  # floor 1.25 > rate 1.0 -> floored
    assert costs["TINY"] == pytest.approx(4.0)  # floor 0.625 < rate 4.0
    assert costs["CHEAP"] == pytest.approx(5.0)  # floor 5.0 > rate 4.0 -> floored


def test_unknown_ticker_is_loud():
    with pytest.raises(ValueError, match="neither tier"):
        tiered_cost_bps_by_ticker(
            ["BIGCO", "MYSTERY"], LARGE, MID_SMALL, 1.0, 4.0, MEDIAN_CLOSES
        )


def test_overlapping_tiers_are_loud():
    with pytest.raises(ValueError, match="tiers overlap"):
        tiered_cost_bps_by_ticker(
            ["BIGCO"], LARGE, ["BIGCO"], 1.0, 4.0, MEDIAN_CLOSES
        )


def test_missing_or_bad_median_close_is_loud():
    with pytest.raises(ValueError, match="no usable median close"):
        tiered_cost_bps_by_ticker(
            ["BIGCO"], LARGE, MID_SMALL, 1.0, 4.0, {}
        )
    with pytest.raises(ValueError, match="no usable median close"):
        tiered_cost_bps_by_ticker(
            ["BIGCO"], LARGE, MID_SMALL, 1.0, 4.0, {"BIGCO": 0.0}
        )


# --- scale_half_spread_frame_to_median ---------------------------------


def _frame(values_by_ticker: dict[str, list[float]], start: str) -> pd.DataFrame:
    index = pd.bdate_range(start, periods=len(next(iter(values_by_ticker.values()))))
    return pd.DataFrame(values_by_ticker, index=index, dtype=float)


def test_scaling_hits_target_median_exactly():
    # 6 charged-region cells with hand-known median. Values in unit
    # fractions (1bp = 1e-4). Cells: 1, 2, 3, 4, 5, 6 bp -> median 3.5bp.
    frame = _frame(
        {"A": [1e-4, 3e-4, 5e-4], "B": [2e-4, 4e-4, 6e-4]},
        start="2026-01-05",
    )
    scaled, scale, observed = scale_half_spread_frame_to_median(
        frame, target_median_half_spread=2e-4, formation_start=date(2026, 1, 1)
    )
    assert observed == pytest.approx(3.5e-4)
    assert scale == pytest.approx(2e-4 / 3.5e-4)
    # every cell scaled by the same scalar, relative structure untouched
    assert scaled.loc[frame.index[0], "A"] == pytest.approx(1e-4 * scale)
    ratio = (scaled / frame).to_numpy()
    assert np.allclose(ratio, scale)
    # and the scaled pooled median is the target by construction
    assert float(pd.Series(scaled.to_numpy().ravel()).median()) == pytest.approx(2e-4)


def test_cells_before_formation_start_are_excluded_from_calibration():
    # Warmup rows carry an absurd 100bp cell that would drag the median if
    # (wrongly) included; formation region is 1bp and 3bp -> median 2bp.
    frame = _frame({"A": [100e-4, 1e-4, 3e-4]}, start="2026-01-05")
    formation_start = frame.index[1].date()
    scaled, scale, observed = scale_half_spread_frame_to_median(
        frame, target_median_half_spread=2e-4, formation_start=formation_start
    )
    assert observed == pytest.approx(2e-4)
    assert scale == pytest.approx(1.0)
    # the warmup cell is still scaled (by the same scalar), never dropped
    assert scaled.iloc[0, 0] == pytest.approx(100e-4)


def test_nan_cells_survive_and_are_ignored_in_calibration():
    frame = _frame({"A": [np.nan, 2e-4], "B": [4e-4, np.nan]}, start="2026-01-05")
    scaled, scale, observed = scale_half_spread_frame_to_median(
        frame, target_median_half_spread=3e-4, formation_start=date(2026, 1, 1)
    )
    assert observed == pytest.approx(3e-4)  # median of {2bp, 4bp}
    assert scale == pytest.approx(1.0)
    assert np.isnan(scaled.iloc[0, 0]) and np.isnan(scaled.iloc[1, 1])


def test_empty_charged_region_is_loud():
    frame = _frame({"A": [1e-4, 2e-4]}, start="2026-01-05")
    with pytest.raises(ValueError, match="no non-NaN half-spread cells"):
        scale_half_spread_frame_to_median(
            frame, target_median_half_spread=2e-4, formation_start=date(2027, 1, 1)
        )


def test_non_positive_target_is_loud():
    frame = _frame({"A": [1e-4]}, start="2026-01-05")
    with pytest.raises(ValueError, match="must be positive"):
        scale_half_spread_frame_to_median(
            frame, target_median_half_spread=0.0, formation_start=date(2026, 1, 1)
        )
