from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional import CrossSectionalData
from app.services.research_lab.cross_sectional_seasonality import (
    MIN_SAME_MONTH_OBSERVATIONS,
    OTHER_MONTH_MODE,
    SAME_MONTH_MODE,
    SEASONALITY_HOLDING_DAYS,
    SEASONALITY_LOOKBACK_YEARS,
    SEASONALITY_RANK_FRACTION,
    SEASONALITY_SKIP_RECENT_MODE,
    SEASONALITY_SPEC_CEILING,
    SEASONALITY_SPECS,
    _complete_monthly_returns,
    run_seasonality_screening,
    signal_same_calendar_month,
    target_calendar_month,
)

# --- synthetic price builder ------------------------------------------------


def _planted_close(
    effects: dict[str, tuple[int, float]],
    start: str = "2000-01-03",
    end: str = "2026-03-20",
    noise: float = 0.0,
    seed: int = 0,
) -> pd.DataFrame:
    """Daily closes for tickers with a PLANTED same-calendar-month effect.

    effects maps ticker -> (calendar month, total extra return spread evenly
    across that month's trading days every single year). A ticker with
    (3, 0.03) gains an extra 3% every March and nothing anywhere else, which
    is exactly the signal KLN's mu-hat is supposed to detect."""
    idx = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    cols = {}
    for ticker, (month, size) in effects.items():
        daily = pd.Series(rng.normal(0.0, noise, len(idx)), index=idx)
        in_month = idx.month == month
        daily[in_month] += size / 21.0
        cols[ticker] = 100.0 * np.exp(daily.cumsum())
    return pd.DataFrame(cols, index=idx)


def _view(close: pd.DataFrame, through: str) -> CrossSectionalData:
    return CrossSectionalData(close=close.loc[:through])


# --- family shape guards (same convention as test_cross_sectional_ivol's) ----


def test_family_is_8_definitions_inside_the_hard_ceiling():
    assert len(SEASONALITY_SPECS) == 8
    assert len(SEASONALITY_SPECS) <= SEASONALITY_SPEC_CEILING


def test_family_pattern_ids_are_unique_and_every_spec_is_cited():
    ids = [s.pattern_id for s in SEASONALITY_SPECS]
    assert len(set(ids)) == len(ids)
    for spec in SEASONALITY_SPECS:
        assert "Keloharju" in spec.citation
        assert "Linnainmaa" in spec.citation
        assert "Nyberg" in spec.citation
        assert "Journal of Finance" in spec.citation
        assert spec.holding_days == SEASONALITY_HOLDING_DAYS
        assert spec.lookback_days > 0
        assert spec.rank_fraction == pytest.approx(SEASONALITY_RANK_FRACTION)
        # Close-only family: no other frame may be silently required.
        assert spec.requires_open is False
        assert spec.requires_volume is False
        assert spec.requires_market_cap is False


def test_family_covers_the_six_same_month_definitions_grid():
    main = [s for s in SEASONALITY_SPECS if s.pattern_id.startswith("seasonality_same_month_")]
    main = [s for s in main if "skip_lag12" not in s.pattern_id]
    assert len(main) == 6
    grid = {(s.lookback_days, s.portfolio) for s in main}
    assert len(grid) == 6
    assert {s.portfolio for s in main} == {"long_short", "long_universe_hedged"}
    # One spec per declared lookback per portfolio mode, no gaps.
    for years in SEASONALITY_LOOKBACK_YEARS:
        matching = [s for s in main if f"_{years}y_" in s.pattern_id]
        assert len(matching) == 2


def test_family_carries_the_placebo_and_the_momentum_purged_control():
    ids = {s.pattern_id for s in SEASONALITY_SPECS}
    assert "seasonality_other_month_placebo_20y_ls" in ids
    assert "seasonality_same_month_skip_lag12_20y_ls" in ids


# --- the core detection test: a planted effect must be found ----------------


def test_planted_same_month_effect_is_detected_and_correctly_ranked():
    close = _planted_close(
        {"MARCH_UP": (3, 0.03), "NEUTRAL": (3, 0.0), "MARCH_DOWN": (3, -0.03)}
    )
    # Formation late February -> the hold lands in March.
    data = _view(close, "2026-02-25")
    assert target_calendar_month(data.close.index[-1], SEASONALITY_HOLDING_DAYS).month == 3

    signal = signal_same_calendar_month(data, lookback_years=20)
    assert signal["MARCH_UP"] > signal["NEUTRAL"] > signal["MARCH_DOWN"]
    # The planted spread is 6% (from +3% to -3%); demeaning is a per-month
    # location shift, so the SPREAD survives it essentially intact.
    assert signal["MARCH_UP"] - signal["MARCH_DOWN"] == pytest.approx(0.06, abs=0.005)


def test_a_stock_without_a_planted_effect_gets_no_seasonal_signal():
    """The negative half of the detection test: the same three tickers,
    ranked for a month nobody has an effect in, must come out flat — a
    detector that fires on the March stocks in June is measuring the
    ticker, not the season."""
    close = _planted_close(
        {"MARCH_UP": (3, 0.03), "NEUTRAL": (3, 0.0), "MARCH_DOWN": (3, -0.03)}
    )
    data = _view(close, "2025-05-27")
    assert target_calendar_month(data.close.index[-1], SEASONALITY_HOLDING_DAYS).month == 6
    signal = signal_same_calendar_month(data, lookback_years=20)
    assert signal.abs().max() == pytest.approx(0.0, abs=1e-9)


def test_effects_planted_in_different_months_do_not_bleed_into_each_other():
    close = _planted_close({"JAN": (1, 0.05), "JUL": (7, 0.05), "FLAT": (1, 0.0)})
    # Target January: only JAN has an effect there. JUL and FLAT are BOTH
    # seasonless in January and must therefore be indistinguishable — they
    # differ only in a month this formation is not ranking on.
    jan = signal_same_calendar_month(_view(close, "2025-12-24"), lookback_years=20)
    assert target_calendar_month(pd.Timestamp("2025-12-24"), 21).month == 1
    assert jan["JAN"] > jan["FLAT"]
    assert jan["JAN"] > jan["JUL"]
    assert jan["JUL"] == pytest.approx(jan["FLAT"], abs=1e-9)
    # Target July: the ranking must fully invert, not merely weaken.
    jul = signal_same_calendar_month(_view(close, "2025-06-25"), lookback_years=20)
    assert target_calendar_month(pd.Timestamp("2025-06-25"), 21).month == 7
    assert jul["JUL"] > jul["FLAT"]
    assert jul["JUL"] > jul["JAN"]
    assert jul["JAN"] == pytest.approx(jul["FLAT"], abs=1e-9)


# --- look-ahead / point-in-time correctness ---------------------------------


def test_future_rows_cannot_change_the_signal():
    """The structural guarantee, tested the way test_cross_sectional_ivol
    tests its own: compute on a view, then rewrite everything AFTER the
    formation date and recompute. Identical, or the signal is reading the
    future."""
    close = _planted_close({"A": (3, 0.03), "B": (3, -0.03), "C": (3, 0.0)}, noise=0.01)
    cutoff = "2026-02-25"
    before = signal_same_calendar_month(_view(close, cutoff), lookback_years=20)

    poisoned = close.copy()
    future_rows = poisoned.index > pd.Timestamp(cutoff)
    poisoned.loc[future_rows] = poisoned.loc[future_rows] * 10.0
    after = signal_same_calendar_month(_view(poisoned, cutoff), lookback_years=20)

    pd.testing.assert_series_equal(before, after)


def test_the_formation_month_itself_is_never_used():
    """A same-calendar-month average must only include months that have
    ALREADY fully happened. Rewriting the in-progress formation month must
    not move the signal — if it does, the signal is ranking on a partial
    month that a real formation could not have observed in full."""
    close = _planted_close({"A": (3, 0.03), "B": (3, -0.03), "C": (3, 0.0)})
    # Mid-March formation: March is the formation month AND the month the
    # planted effect lives in, so this is the hardest version of the check.
    cutoff = "2026-03-13"
    before = signal_same_calendar_month(_view(close, cutoff), lookback_years=20)

    poisoned = close.copy()
    march_2026 = (poisoned.index.year == 2026) & (poisoned.index.month == 3)
    poisoned.loc[march_2026] = poisoned.loc[march_2026] * 3.0
    after = signal_same_calendar_month(_view(poisoned, cutoff), lookback_years=20)

    pd.testing.assert_series_equal(before, after)


def test_complete_monthly_returns_stops_before_the_formation_month():
    close = _planted_close({"A": (3, 0.01), "B": (3, 0.0)}, end="2026-03-20")
    monthly = _complete_monthly_returns(close.loc[:"2026-03-13"])
    assert monthly.index.to_period("M").max() == pd.Period("2026-02", freq="M")


def test_every_selected_month_is_at_least_eleven_months_before_formation():
    """The lag algebra's own guarantee, checked directly rather than
    inferred: the minimum admitted target-month lag is 12 and the target
    month is at most one month past the formation month, so nothing inside
    a year of the formation can be selected."""
    close = _planted_close({"A": (3, 0.01), "B": (3, 0.0)})
    for cutoff in ("2026-02-25", "2026-03-13", "2025-12-31", "2025-01-05"):
        view = _view(close, cutoff)
        formation = view.close.index[-1].to_period("M")
        monthly = _complete_monthly_returns(view.close)
        target = target_calendar_month(view.close.index[-1], SEASONALITY_HOLDING_DAYS)
        lags = target.ordinal - monthly.index.to_period("M").asi8
        selected = monthly.index[(lags >= 12) & (lags <= 240)]
        assert len(selected) > 0
        newest = selected.to_period("M").max()
        assert (formation.ordinal - newest.ordinal) >= 11


# --- mode semantics ---------------------------------------------------------


def test_skip_lag12_mode_drops_exactly_the_most_recent_same_month_observation():
    """The momentum-purged control. A ticker whose planted effect exists in
    EVERY prior March except the most recent one must look identical under
    both modes; a ticker whose effect exists ONLY in the most recent March
    must vanish under skip-lag-12."""
    idx = pd.bdate_range("2000-01-03", "2026-02-25")
    rng = np.random.default_rng(3)
    only_last_march = pd.Series(0.0, index=idx)
    last_march = (idx.year == 2025) & (idx.month == 3)
    only_last_march[last_march] = 0.10 / 21.0
    cols = {
        "ONLY_LAST": 100 * np.exp(only_last_march.cumsum()),
        "FLAT": 100 * np.exp(pd.Series(0.0, index=idx).cumsum()),
        "NOISE": 100 * np.exp(pd.Series(rng.normal(0, 1e-6, len(idx)), index=idx).cumsum()),
    }
    data = CrossSectionalData(close=pd.DataFrame(cols, index=idx))

    kept = signal_same_calendar_month(data, lookback_years=20, mode=SAME_MONTH_MODE)
    skipped = signal_same_calendar_month(data, lookback_years=20, mode=SEASONALITY_SKIP_RECENT_MODE)

    # With lag 12 included, the single big March shows up in the average.
    assert kept["ONLY_LAST"] > kept["FLAT"]
    # With lag 12 dropped, there is nothing left of it.
    assert skipped["ONLY_LAST"] == pytest.approx(skipped["FLAT"], abs=1e-6)


def test_other_month_mode_ignores_the_target_month_entirely():
    """KLN's placebo must be blind to the very effect the same-month mode
    is built to see."""
    close = _planted_close({"MARCH_UP": (3, 0.05), "FLAT": (3, 0.0)})
    data = _view(close, "2026-02-25")
    same = signal_same_calendar_month(data, lookback_years=20, mode=SAME_MONTH_MODE)
    other = signal_same_calendar_month(data, lookback_years=20, mode=OTHER_MONTH_MODE)
    assert same["MARCH_UP"] > same["FLAT"]
    assert other["MARCH_UP"] == pytest.approx(other["FLAT"], abs=1e-9)


def test_unknown_mode_is_rejected_loudly():
    close = _planted_close({"A": (3, 0.01), "B": (3, 0.0)})
    with pytest.raises(ValueError, match="unknown same-calendar-month mode"):
        signal_same_calendar_month(_view(close, "2026-02-25"), lookback_years=20, mode="sideways")


# --- data floors ------------------------------------------------------------


def test_short_history_ticker_gets_no_signal():
    """KLN's own floor: 'We include stocks that have at least five years of
    historical data at time t.' A ticker with four target-month
    observations must be NaN, not a noisy guess."""
    close = _planted_close({"A": (3, 0.02), "B": (3, 0.0)}, start="2000-01-03")
    ipo = close.copy()
    # B only starts trading four Marches before the formation.
    ipo.loc[ipo.index < pd.Timestamp("2022-01-01"), "B"] = np.nan
    signal = signal_same_calendar_month(_view(ipo, "2026-02-25"), lookback_years=20)
    assert np.isnan(signal["B"])
    assert not np.isnan(signal["A"])


def test_exactly_the_minimum_number_of_observations_is_admitted():
    close = _planted_close({"A": (3, 0.02), "B": (3, 0.0)}, start="2000-01-03")
    ipo = close.copy()
    # Five Marches (2021..2025) precede a 2026-02 formation.
    ipo.loc[ipo.index < pd.Timestamp("2021-01-01"), "B"] = np.nan
    signal = signal_same_calendar_month(_view(ipo, "2026-02-25"), lookback_years=20)
    assert not np.isnan(signal["B"])
    assert MIN_SAME_MONTH_OBSERVATIONS == 5


def test_a_shorter_lookback_uses_strictly_fewer_observations():
    close = _planted_close({"A": (3, 0.02), "B": (3, 0.0)}, noise=0.02, seed=7)
    data = _view(close, "2026-02-25")
    long_window = signal_same_calendar_month(data, lookback_years=20)
    short_window = signal_same_calendar_month(data, lookback_years=5)
    # Different windows, genuinely different averages (not a silently
    # ignored parameter).
    assert long_window["A"] != short_window["A"]


def test_empty_or_tiny_history_returns_all_nan_rather_than_raising():
    idx = pd.bdate_range("2026-01-02", periods=5)
    data = CrossSectionalData(close=pd.DataFrame({"A": 100.0, "B": 100.0}, index=idx))
    signal = signal_same_calendar_month(data, lookback_years=20)
    assert signal.isna().all()
    assert list(signal.index) == ["A", "B"]


# --- target-month resolution ------------------------------------------------


def test_target_month_follows_the_midpoint_of_the_upcoming_hold():
    # Late in the month -> the 21-day hold lands mostly in the NEXT month.
    assert target_calendar_month(pd.Timestamp("2026-03-27"), 21) == pd.Period("2026-04", "M")
    # Early in the month -> the hold lands mostly in THIS month.
    assert target_calendar_month(pd.Timestamp("2026-03-03"), 21) == pd.Period("2026-03", "M")
    # Year boundary.
    assert target_calendar_month(pd.Timestamp("2025-12-28"), 21) == pd.Period("2026-01", "M")


# --- production entry point guard ------------------------------------------


def test_screening_rejects_start_before_membership_coverage():
    with pytest.raises(ValueError, match="predates point-in-time membership coverage"):
        run_seasonality_screening(date(2010, 1, 4), date(2020, 1, 1))
