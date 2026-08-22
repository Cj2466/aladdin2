from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np
from scipy.stats import linregress

from app.services.macro_data.base import MacroObservationResult

REGRESSION_WINDOW_TRADING_DAYS = 60  # ~1 quarter — smooths noise, stays in-regime
FORECAST_HORIZON_TRADING_DAYS = 21  # ~1 month
LONG_LOOKBACK_TRADING_DAYS = 1260  # ~5 years, cap on the empirical-band lookback
MIN_HISTORY_FOR_BAND_TRADING_DAYS = 250  # ~1 year floor — below this, refuse to project

# Administratively set by the FOMC in discrete steps, not market-determined
# — a trend fit either produces a near-zero-variance line during a hold
# period or extrapolates a hiking/cutting cycle indefinitely. Excluded
# deliberately, not an oversight.
PROJECTABLE_SERIES_IDS: tuple[str, ...] = ("DGS3MO", "DGS2", "DGS10", "DGS30", "T10Y2Y", "T10YIE")


@dataclass
class SeriesProjection:
    status: Literal["ok", "insufficient_history"]
    as_of_date: date | None
    last_value: float | None
    regression_window_size: int
    point_estimate: float | None
    band_low: float | None
    band_high: float | None
    r_squared: float | None
    trend_strength: Literal["weak", "moderate", "strong"] | None
    point_estimate_outside_historical_range: bool | None


def compute_series_projection(history: list[MacroObservationResult]) -> SeriesProjection:
    """A real short-horizon numeric projection, not a prediction dressed up
    as one: the point estimate is a plain linear trend over a recent
    window, and the band is the EMPIRICAL historical dispersion of
    realized 21-trading-day-ahead changes (the same percentile technique
    this codebase already uses for historical_var), anchored to the last
    observed value — not a Gaussian confidence interval from the
    regression's own standard error, which would assume i.i.d. normal
    residuals (false for a trending rate series) and compound one
    false-precision claim with another."""
    if len(history) < MIN_HISTORY_FOR_BAND_TRADING_DAYS + FORECAST_HORIZON_TRADING_DAYS:
        return SeriesProjection("insufficient_history", None, None, 0, None, None, None, None, None, None)

    values = np.array([o.value for o in history])
    window = values[-REGRESSION_WINDOW_TRADING_DAYS:]
    last_value = float(values[-1])

    if np.std(window) == 0:  # flat window — guard linregress's degenerate case
        point_estimate, r_squared, p_value = last_value, 0.0, 1.0
    else:
        x = np.arange(len(window))
        slope, intercept, r_value, p_value, _std_err = linregress(x, window)
        point_estimate = float(intercept + slope * (len(window) - 1 + FORECAST_HORIZON_TRADING_DAYS))
        r_squared = float(r_value**2)

    long_slice = values[-(LONG_LOOKBACK_TRADING_DAYS + FORECAST_HORIZON_TRADING_DAYS) :]
    deltas = long_slice[FORECAST_HORIZON_TRADING_DAYS:] - long_slice[:-FORECAST_HORIZON_TRADING_DAYS]
    p10, p90 = np.percentile(deltas, [10, 90])
    band_low, band_high = last_value + float(p10), last_value + float(p90)
    band_low, band_high = min(band_low, band_high), max(band_low, band_high)

    trend_strength: Literal["weak", "moderate", "strong"]
    if p_value > 0.05 or r_squared < 0.1:
        trend_strength = "weak"
    elif r_squared < 0.4:
        trend_strength = "moderate"
    else:
        trend_strength = "strong"

    outside = point_estimate < band_low or point_estimate > band_high

    return SeriesProjection(
        status="ok",
        as_of_date=history[-1].observation_date,
        last_value=last_value,
        regression_window_size=len(window),
        point_estimate=point_estimate,
        band_low=band_low,
        band_high=band_high,
        r_squared=r_squared,
        trend_strength=trend_strength,
        point_estimate_outside_historical_range=outside,
    )
