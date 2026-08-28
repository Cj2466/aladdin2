from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional import CrossSectionalData
from app.services.research_lab.cross_sectional_illiq import (
    AMIHUD_SCALE,
    ILLIQ_BASELINE_MONTHS,
    ILLIQ_HOLDING_HORIZONS_DAYS,
    ILLIQ_MEAN_SCALED_MODE,
    ILLIQ_RANK_FRACTION,
    ILLIQ_SHORT_BASELINE_MONTHS,
    ILLIQ_SPEC_CEILING,
    ILLIQ_SPECS,
    ILLIQ_STANDARDIZED_MODE,
    MIN_DAILY_OBSERVATIONS_PER_BLOCK,
    TRADING_DAYS_PER_MONTH,
    _block_illiq,
    amihud_illiq_daily_ratio,
    run_illiq_screening,
    signal_liquidity_shock,
)

N_BLOCKS = ILLIQ_BASELINE_MONTHS + 1
N_ROWS = N_BLOCKS * TRADING_DAYS_PER_MONTH


def _shock_data(
    shocks: dict[str, float],
    *,
    n_rows: int = N_ROWS,
    baseline_volume: float = 1e7,
    seed: int = 1,
    baseline_jitter: float = 0.05,
) -> CrossSectionalData:
    """Identical price paths for every ticker; ONLY the last 21 days' volume
    differs, by the per-ticker multiplier in `shocks`.

    Holding the return series fixed across tickers is what makes this a
    clean test of the LIQUIDITY channel: any difference in the resulting
    LIQU can only have come from dollar volume, since |R| is shared. A
    multiplier < 1 is a volume collapse (illiquidity SPIKES -> a NEGATIVE
    liquidity shock); > 1 is a volume surge (a POSITIVE shock)."""
    idx = pd.bdate_range("2020-01-01", periods=n_rows)
    rng = np.random.default_rng(seed)
    path = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, n_rows)))
    close = pd.DataFrame({t: path for t in shocks}, index=idx)
    volume = pd.DataFrame({t: np.full(n_rows, baseline_volume) for t in shocks}, index=idx)
    if baseline_jitter:
        jitter = 1 + rng.normal(0.0, baseline_jitter, volume.iloc[:-TRADING_DAYS_PER_MONTH].shape)
        volume.iloc[:-TRADING_DAYS_PER_MONTH] = volume.iloc[:-TRADING_DAYS_PER_MONTH] * jitter
    for ticker, multiplier in shocks.items():
        volume.loc[idx[-TRADING_DAYS_PER_MONTH:], ticker] = baseline_volume * multiplier
    return CrossSectionalData(close=close, volume=volume)


# --- family shape guards ----------------------------------------------------


def test_family_is_8_definitions_inside_the_hard_ceiling():
    assert len(ILLIQ_SPECS) == 8
    assert len(ILLIQ_SPECS) <= ILLIQ_SPEC_CEILING


def test_family_pattern_ids_are_unique_and_every_spec_is_cited():
    ids = [s.pattern_id for s in ILLIQ_SPECS]
    assert len(set(ids)) == len(ids)
    for spec in ILLIQ_SPECS:
        assert "Bali" in spec.citation
        assert "Peng" in spec.citation
        assert "Shen" in spec.citation
        assert "Tang" in spec.citation
        assert "Amihud" in spec.citation
        assert "Review of Financial Studies" in spec.citation
        assert spec.rank_fraction == pytest.approx(ILLIQ_RANK_FRACTION)
        assert spec.lookback_days > 0


def test_the_citation_records_the_continuation_direction_not_a_reversal():
    """The scoping brief guessed 'reversal'; the paper says the market
    UNDERREACTS and returns CONTINUE. That correction is load-bearing for
    the sign of every long_short leg in this family, so it is pinned in the
    citation string rather than living only in prose."""
    for spec in ILLIQ_SPECS:
        assert "continuation, not a reversal" in spec.citation
        assert "UNDERREACTS" in spec.citation


def test_every_spec_declares_the_volume_frame_it_reads():
    for spec in ILLIQ_SPECS:
        assert spec.requires_volume is True
        assert spec.requires_open is False
        assert spec.requires_market_cap is False


def test_family_covers_the_six_standardized_definitions_grid():
    main = [s for s in ILLIQ_SPECS if s.pattern_id.startswith("illiq_shock_std_h")]
    assert len(main) == 6
    assert {s.holding_days for s in main} == set(ILLIQ_HOLDING_HORIZONS_DAYS)
    assert {s.portfolio for s in main} == {"long_short", "long_universe_hedged"}
    assert len({(s.holding_days, s.portfolio) for s in main}) == 6


def test_family_carries_both_robustness_definitions():
    ids = {s.pattern_id for s in ILLIQ_SPECS}
    assert "illiq_shock_mean_scaled_h21_ls" in ids
    assert "illiq_shock_std_base6m_h21_ls" in ids
    short = next(s for s in ILLIQ_SPECS if s.pattern_id == "illiq_shock_std_base6m_h21_ls")
    twelve = next(s for s in ILLIQ_SPECS if s.pattern_id == "illiq_shock_std_h21_ls")
    assert short.lookback_days < twelve.lookback_days


def test_the_six_month_continuation_horizon_is_actually_covered():
    """The paper's headline claim is a continuation lasting 'up to six
    months'. A family that only ever held one month could not test it."""
    assert 126 in ILLIQ_HOLDING_HORIZONS_DAYS
    assert any(s.holding_days == 126 for s in ILLIQ_SPECS)


# --- the Amihud formula itself ---------------------------------------------


def test_daily_ratio_matches_a_hand_computed_amihud_ratio():
    idx = pd.bdate_range("2024-01-01", periods=3)
    close = pd.DataFrame({"A": [100.0, 110.0, 99.0]}, index=idx)
    volume = pd.DataFrame({"A": [1_000.0, 2_000.0, 4_000.0]}, index=idx)
    ratio = amihud_illiq_daily_ratio(close, volume)
    assert np.isnan(ratio["A"].iloc[0])  # no prior close, so no return
    # day 2: |+0.10| / (110 * 2000) * 1e6
    assert ratio["A"].iloc[1] == pytest.approx(abs(0.10) / (110.0 * 2_000.0) * AMIHUD_SCALE)
    # day 3: |(99-110)/110| / (99 * 4000) * 1e6
    assert ratio["A"].iloc[2] == pytest.approx(abs(-11.0 / 110.0) / (99.0 * 4_000.0) * AMIHUD_SCALE)


def test_zero_and_negative_dollar_volume_become_nan_not_infinity():
    """A zero-volume day must not hand the ticker an infinite ILLIQ that
    would then poison every mean and standard deviation downstream."""
    idx = pd.bdate_range("2024-01-01", periods=3)
    close = pd.DataFrame({"A": [100.0, 110.0, 121.0]}, index=idx)
    volume = pd.DataFrame({"A": [1_000.0, 0.0, 1_000.0]}, index=idx)
    ratio = amihud_illiq_daily_ratio(close, volume)
    assert np.isnan(ratio["A"].iloc[1])
    assert np.isfinite(ratio["A"].iloc[2])


def test_block_illiq_averages_exactly_21_trailing_rows():
    idx = pd.bdate_range("2024-01-01", periods=TRADING_DAYS_PER_MONTH * 3)
    ratio = pd.DataFrame({"A": np.arange(len(idx), dtype=float)}, index=idx)
    newest = _block_illiq(ratio, 0)
    older = _block_illiq(ratio, 1)
    n = TRADING_DAYS_PER_MONTH
    assert newest["A"] == pytest.approx(np.arange(2 * n, 3 * n).mean())
    assert older["A"] == pytest.approx(np.arange(n, 2 * n).mean())


def test_block_with_too_few_daily_observations_is_nan():
    """'A firm is required to have at least 15 daily return observations in
    month t' — the paper's own floor, applied to every block."""
    idx = pd.bdate_range("2024-01-01", periods=TRADING_DAYS_PER_MONTH * 2)
    values = np.arange(len(idx), dtype=float)
    ratio = pd.DataFrame({"THIN": values.copy(), "FULL": values.copy()}, index=idx)
    # Leave THIN with 14 usable observations in the newest block.
    keep = TRADING_DAYS_PER_MONTH - MIN_DAILY_OBSERVATIONS_PER_BLOCK + 1
    ratio.iloc[-TRADING_DAYS_PER_MONTH : -TRADING_DAYS_PER_MONTH + keep, 0] = np.nan
    block = _block_illiq(ratio, 0)
    assert np.isnan(block["THIN"])
    assert np.isfinite(block["FULL"])


def test_block_beyond_available_history_is_all_nan():
    idx = pd.bdate_range("2024-01-01", periods=TRADING_DAYS_PER_MONTH)
    ratio = pd.DataFrame({"A": np.ones(len(idx))}, index=idx)
    assert _block_illiq(ratio, 5).isna().all()


# --- the core detection test: a planted shock must be found, with the
# --- paper's sign ----------------------------------------------------------


def test_planted_liquidity_shock_is_detected_with_the_papers_sign():
    """Footnote 6: 'positive (negative) liquidity shock indicates an
    increase (decrease) in liquidity relative to its past 12-month
    average.' A volume collapse is an illiquidity spike, which must produce
    a NEGATIVE LIQU and therefore land in the SHORT leg."""
    data = _shock_data({"COLLAPSE": 0.1, "STEADY": 1.0, "SURGE": 10.0})
    signal = signal_liquidity_shock(data)
    assert signal["COLLAPSE"] < 0
    assert signal["SURGE"] > 0
    assert signal["SURGE"] > signal["STEADY"] > signal["COLLAPSE"]


def test_the_shock_is_measured_against_the_ticker_own_baseline_not_the_level():
    """Two tickers with identical SHOCKS but illiquidity levels an order of
    magnitude apart must receive near-identical LIQU. This is the whole
    point of differencing and standardizing against each ticker's own
    trailing window — without it the family would rank on the Amihud LEVEL,
    which is a different (and already well-known) anomaly."""
    idx = pd.bdate_range("2020-01-01", periods=N_ROWS)
    rng = np.random.default_rng(11)
    path = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, N_ROWS)))
    close = pd.DataFrame({"THICK": path, "THIN": path}, index=idx)
    base = rng.normal(1.0, 0.05, N_ROWS)
    volume = pd.DataFrame(
        {"THICK": base * 1e9, "THIN": base * 1e6},  # 1000x different LEVEL
        index=idx,
    )
    # Identical proportional shock in the newest block.
    volume.iloc[-TRADING_DAYS_PER_MONTH:] = volume.iloc[-TRADING_DAYS_PER_MONTH:] * 0.5
    signal = signal_liquidity_shock(CrossSectionalData(close=close, volume=volume))
    assert signal["THICK"] == pytest.approx(signal["THIN"], rel=1e-6)
    assert signal["THICK"] < 0  # both suffered the same illiquidity spike


def test_mean_scaled_mode_ranks_the_same_direction_but_is_a_different_number():
    data = _shock_data({"COLLAPSE": 0.1, "STEADY": 1.0, "SURGE": 10.0})
    std = signal_liquidity_shock(data, mode=ILLIQ_STANDARDIZED_MODE)
    mean_scaled = signal_liquidity_shock(data, mode=ILLIQ_MEAN_SCALED_MODE)
    assert mean_scaled["SURGE"] > mean_scaled["STEADY"] > mean_scaled["COLLAPSE"]
    # Genuinely a different measure, not a silently ignored parameter.
    assert std["COLLAPSE"] != pytest.approx(mean_scaled["COLLAPSE"])


def test_a_ticker_whose_illiquidity_never_moves_gets_no_signal():
    """Zero baseline dispersion makes a standardized shock undefined, not
    infinite."""
    idx = pd.bdate_range("2020-01-01", periods=N_ROWS)
    close = pd.DataFrame({"FROZEN": np.full(N_ROWS, 100.0)}, index=idx)
    volume = pd.DataFrame({"FROZEN": np.full(N_ROWS, 1e7)}, index=idx)
    signal = signal_liquidity_shock(CrossSectionalData(close=close, volume=volume))
    assert np.isnan(signal["FROZEN"])


def test_unknown_mode_is_rejected_loudly():
    data = _shock_data({"A": 0.5, "B": 1.0})
    with pytest.raises(ValueError, match="unknown liquidity-shock mode"):
        signal_liquidity_shock(data, mode="sideways")


def test_missing_volume_frame_fails_loudly_rather_than_silently_ranking_nothing():
    idx = pd.bdate_range("2020-01-01", periods=N_ROWS)
    data = CrossSectionalData(close=pd.DataFrame({"A": np.ones(N_ROWS)}, index=idx))
    with pytest.raises(ValueError, match="needs CrossSectionalData.volume"):
        signal_liquidity_shock(data)


# --- look-ahead / point-in-time correctness ---------------------------------


def test_future_rows_cannot_change_the_signal():
    data = _shock_data({"COLLAPSE": 0.1, "STEADY": 1.0, "SURGE": 10.0}, n_rows=N_ROWS + 60)
    cutoff = N_ROWS
    view = CrossSectionalData(close=data.close.iloc[:cutoff], volume=data.volume.iloc[:cutoff])
    before = signal_liquidity_shock(view)

    poisoned_close = data.close.copy()
    poisoned_volume = data.volume.copy()
    poisoned_close.iloc[cutoff:] = poisoned_close.iloc[cutoff:] * 5.0
    poisoned_volume.iloc[cutoff:] = poisoned_volume.iloc[cutoff:] * 0.001
    after = signal_liquidity_shock(
        CrossSectionalData(
            close=poisoned_close.iloc[:cutoff], volume=poisoned_volume.iloc[:cutoff]
        )
    )
    pd.testing.assert_series_equal(before, after)


def test_the_shock_window_never_reaches_into_the_holding_window():
    """The specific check the build called for: the block grid is counted
    BACKWARD from the formation row, so the newest block ends ON the
    formation date and nothing later is touched. Rewriting exactly the rows
    a 126-day hold would occupy must leave the signal bit-identical."""
    longest_hold = max(ILLIQ_HOLDING_HORIZONS_DAYS)
    data = _shock_data({"A": 0.2, "B": 1.0, "C": 5.0}, n_rows=N_ROWS + longest_hold)
    formation = N_ROWS
    view = CrossSectionalData(
        close=data.close.iloc[:formation], volume=data.volume.iloc[:formation]
    )
    before = signal_liquidity_shock(view)

    poisoned_close = data.close.copy()
    poisoned_volume = data.volume.copy()
    hold_rows = slice(formation, formation + longest_hold)
    poisoned_close.iloc[hold_rows] = 1.0
    poisoned_volume.iloc[hold_rows] = 1.0
    after = signal_liquidity_shock(
        CrossSectionalData(
            close=poisoned_close.iloc[:formation], volume=poisoned_volume.iloc[:formation]
        )
    )
    pd.testing.assert_series_equal(before, after)


def test_the_baseline_window_never_overlaps_the_shock_month():
    """month t and the baseline t-12..t-1 must be disjoint: rewriting ONLY
    the newest block must not move the baseline mean, and rewriting ONLY
    the oldest baseline block must not move month t's ILLIQ."""
    data = _shock_data({"A": 1.0, "B": 1.0}, baseline_jitter=0.05)
    ratio = amihud_illiq_daily_ratio(data.close, data.volume)
    current_before = _block_illiq(ratio, 0)
    oldest_before = _block_illiq(ratio, ILLIQ_BASELINE_MONTHS)

    bumped_volume = data.volume.copy()
    bumped_volume.iloc[-TRADING_DAYS_PER_MONTH:] *= 100.0
    bumped = amihud_illiq_daily_ratio(data.close, bumped_volume)
    # Newest block changed; the oldest baseline block did not.
    assert _block_illiq(bumped, 0)["A"] != pytest.approx(current_before["A"])
    assert _block_illiq(bumped, ILLIQ_BASELINE_MONTHS)["A"] == pytest.approx(oldest_before["A"])


# --- data floors ------------------------------------------------------------


def test_too_little_history_returns_all_nan_rather_than_raising():
    data = _shock_data({"A": 0.5, "B": 1.0}, n_rows=TRADING_DAYS_PER_MONTH * 3)
    signal = signal_liquidity_shock(data, baseline_months=ILLIQ_BASELINE_MONTHS)
    assert signal.isna().all()
    assert list(signal.index) == ["A", "B"]


def test_a_thin_baseline_disqualifies_the_ticker():
    """Below MIN_BASELINE_COVERAGE_FRACTION of the baseline window the
    ticker gets no signal — a mean and standard deviation over three
    surviving months is not the paper's 12-month baseline."""
    data = _shock_data({"THIN": 0.2, "FULL": 0.2})
    volume = data.volume.copy()
    # Wipe volume for all but the newest 4 blocks, leaving THIN with 3
    # usable baseline months out of 12.
    keep = 4 * TRADING_DAYS_PER_MONTH
    volume.iloc[:-keep, volume.columns.get_loc("THIN")] = 0.0
    signal = signal_liquidity_shock(CrossSectionalData(close=data.close, volume=volume))
    assert np.isnan(signal["THIN"])
    assert np.isfinite(signal["FULL"])


def test_the_short_baseline_variant_needs_strictly_less_history():
    n_rows = (ILLIQ_SHORT_BASELINE_MONTHS + 1) * TRADING_DAYS_PER_MONTH
    data = _shock_data({"A": 0.2, "B": 1.0, "C": 5.0}, n_rows=n_rows)
    short = signal_liquidity_shock(data, baseline_months=ILLIQ_SHORT_BASELINE_MONTHS)
    twelve = signal_liquidity_shock(data, baseline_months=ILLIQ_BASELINE_MONTHS)
    assert short.notna().all()
    assert twelve.isna().all()  # not enough rows for a 12-month baseline
    assert short["C"] > short["B"] > short["A"]


# --- production entry point guard ------------------------------------------


def test_screening_rejects_start_before_membership_coverage():
    with pytest.raises(ValueError, match="predates point-in-time membership coverage"):
        run_illiq_screening(date(2010, 1, 4), date(2020, 1, 1))
