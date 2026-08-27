from datetime import date

import numpy as np
import pandas as pd
import pytest

import app.services.research_lab.vol_regime_timing as vrt
from app.services.research_lab.vol_regime_timing import (
    CROSS_ASSET_COMPONENTS,
    CROSS_ASSET_MAX_VIX_CORRELATION,
    CROSS_ASSET_MIN_COMPONENTS,
    MIN_REPLAY_TRADING_DAYS,
    TARGET_CREDIT_VS_DURATION,
    TARGET_EQUITY_VS_DURATION,
    TRADED_UNIVERSE,
    VOL_INDEX_FFILL_LIMIT_DAYS,
    VOL_INDEX_UNIVERSE,
    VOL_INDEX_VIX_CORRELATIONS,
    VOL_REGIME_COST_BPS,
    VOL_REGIME_DIRECTION,
    VOL_REGIME_FAMILY,
    VOL_REGIME_HOLDING_DAYS,
    VOL_REGIME_MIN_HOLDING_DAYS,
    VOL_REGIME_N_TRIALS,
    VOL_REGIME_TARGETS,
    VOL_REGIME_Z_WINDOW,
    TimingSpec,
    VolRegimeConfig,
    VolRegimeData,
    align_vol_regime_data,
    block_bootstrap_sharpe_pvalue,
    build_vol_regime_disclosure,
    compute_confound_diagnostics,
    default_vol_regime_config,
    run_timing_backtest,
    run_vol_regime_screening,
    screen_vol_regime_timing,
    state_cross_asset_composite,
    state_ratio,
    trailing_zscore,
)

# --- synthetic-data helpers -----------------------------------------------

# Long enough for the 252-day z warmup plus a comfortable number of
# non-overlapping 63-day holds on top of it.
_N_DAYS = 1400
_START = "2010-01-04"


def _calendar(n: int = _N_DAYS) -> pd.DatetimeIndex:
    return pd.bdate_range(_START, periods=n)


def _flat_vol_frame(index: pd.DatetimeIndex, level: float = 20.0) -> pd.DataFrame:
    return pd.DataFrame(
        {t: np.full(len(index), level, dtype=float) for t in VOL_INDEX_UNIVERSE}, index=index
    )


def _random_walk(index: pd.DatetimeIndex, seed: int, drift: float = 0.0, vol: float = 0.01):
    rng = np.random.default_rng(seed)
    steps = rng.normal(drift, vol, len(index))
    return pd.Series(100.0 * np.exp(np.cumsum(steps)), index=index)


def _traded_frame(index: pd.DatetimeIndex, seed: int = 7) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SPY": _random_walk(index, seed, drift=0.0003, vol=0.011),
            "IEF": _random_walk(index, seed + 1, drift=0.0001, vol=0.004),
            "HYG": _random_walk(index, seed + 2, drift=0.0002, vol=0.006),
        },
        index=index,
    )


def _noisy_vol_frame(index: pd.DatetimeIndex, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    data = {}
    for i, t in enumerate(VOL_INDEX_UNIVERSE):
        data[t] = 20.0 * np.exp(np.cumsum(rng.normal(0, 0.02, len(index))))
    return pd.DataFrame(data, index=index)


def _data(vol: pd.DataFrame, traded: pd.DataFrame) -> VolRegimeData:
    return align_vol_regime_data(vol, traded)


def _spec(
    state_fn=None,
    holding_days: int = 21,
    target=TARGET_EQUITY_VS_DURATION,
    direction: float = VOL_REGIME_DIRECTION,
    z_window: int = VOL_REGIME_Z_WINDOW,
) -> TimingSpec:
    if state_fn is None:
        state_fn = vrt.partial(state_ratio, numerator=vrt.MOVE, denominator=vrt.VIX)
    return TimingSpec(
        spec_id="test_spec",
        state_key="test",
        citation="test citation",
        hypothesis="test hypothesis",
        state_fn=state_fn,
        holding_days=holding_days,
        target=target,
        direction=direction,
        z_window=z_window,
    )


def _config(**kwargs) -> VolRegimeConfig:
    base = {
        "cost_bps": VOL_REGIME_COST_BPS,
        "short_borrow_bps_per_year": vrt.VOL_REGIME_SHORT_BORROW_BPS_PER_YEAR,
        "formation_start": date(2010, 1, 4),
    }
    base.update(kwargs)
    return VolRegimeConfig(**base)


# --- family declaration ----------------------------------------------------


def test_family_is_exactly_the_declared_grid():
    """The 48 is the DSR denominator — it must equal the literal product of
    the declared axes, not merely be asserted somewhere."""
    assert len(VOL_REGIME_FAMILY) == VOL_REGIME_N_TRIALS == 48
    n_states = len({s.state_key for s in VOL_REGIME_FAMILY})
    assert n_states == 8
    assert n_states * len(VOL_REGIME_HOLDING_DAYS) * len(VOL_REGIME_TARGETS) == 48
    assert sorted({s.holding_days for s in VOL_REGIME_FAMILY}) == [21, 42, 63]
    assert {s.target.key for s in VOL_REGIME_FAMILY} == {"spy_ief", "hyg_ief"}


def test_family_spec_ids_are_unique():
    assert len({s.spec_id for s in VOL_REGIME_FAMILY}) == len(VOL_REGIME_FAMILY)


def test_every_spec_covers_each_state_holding_target_cell_exactly_once():
    cells = [(s.state_key, s.holding_days, s.target.key) for s in VOL_REGIME_FAMILY]
    assert len(set(cells)) == len(cells) == 48


def test_direction_is_uniform_and_never_fitted_per_spec():
    """A per-spec sign would double the real search to 96 while still
    reporting n_trials=48 — the exact uncounted degree of freedom the DSR
    exists to prevent."""
    assert {s.direction for s in VOL_REGIME_FAMILY} == {VOL_REGIME_DIRECTION}
    assert VOL_REGIME_DIRECTION == -1.0


def test_no_sub_21_day_holding_periods():
    assert min(s.holding_days for s in VOL_REGIME_FAMILY) >= VOL_REGIME_MIN_HOLDING_DAYS
    assert VOL_REGIME_MIN_HOLDING_DAYS == 21


def test_z_window_is_fixed_not_searched():
    assert {s.z_window for s in VOL_REGIME_FAMILY} == {VOL_REGIME_Z_WINDOW}


def test_family_build_asserts_on_grid_drift(monkeypatch):
    """If someone adds a holding period without updating VOL_REGIME_N_TRIALS,
    the build must fail loudly rather than silently changing the DSR
    denominator."""
    monkeypatch.setattr(vrt, "VOL_REGIME_HOLDING_DAYS", (21, 42, 63, 126))
    with pytest.raises(AssertionError, match="VOL_REGIME_N_TRIALS"):
        vrt._build_vol_regime_family()


def test_every_spec_carries_a_citation_and_hypothesis():
    for spec in VOL_REGIME_FAMILY:
        assert len(spec.citation) > 40
        assert len(spec.hypothesis) > 10


def test_only_independent_indices_are_labelled_cross_asset():
    """^VXN (0.919) and ^VVIX (0.822) co-move with ^VIX far too closely to be
    called cross-ASSET; mislabelling them would let a within-equity result be
    read as evidence for the family's actual claim."""
    for spec in VOL_REGIME_FAMILY:
        if spec.state_key in {"vxn_vix", "vvix_vix", "skew", "vix_level"}:
            assert not spec.is_cross_asset
        if spec.state_key in {"move_vix", "ovx_vix", "gvz_vix", "cross_asset"}:
            assert spec.is_cross_asset


def test_cross_asset_components_respect_the_correlation_threshold():
    for ticker in CROSS_ASSET_COMPONENTS:
        assert VOL_INDEX_VIX_CORRELATIONS[ticker] < CROSS_ASSET_MAX_VIX_CORRELATION
    for excluded in (vrt.VXN, vrt.VVIX):
        assert VOL_INDEX_VIX_CORRELATIONS[excluded] > CROSS_ASSET_MAX_VIX_CORRELATION


def test_vix_level_control_spec_exists():
    """The control is load-bearing: without it nothing in the family tests
    whether cross-asset vol beats plain equity vol."""
    control = [s for s in VOL_REGIME_FAMILY if s.state_key == "vix_level"]
    assert len(control) == len(VOL_REGIME_HOLDING_DAYS) * len(VOL_REGIME_TARGETS) == 6


def test_targets_share_the_risk_off_leg_and_orient_risk_on_consistently():
    assert TARGET_EQUITY_VS_DURATION.risk_off == TARGET_CREDIT_VS_DURATION.risk_off == "IEF"
    assert TARGET_EQUITY_VS_DURATION.risk_on == "SPY"
    assert TARGET_CREDIT_VS_DURATION.risk_on == "HYG"
    for target in VOL_REGIME_TARGETS:
        assert target.risk_on in TRADED_UNIVERSE
        assert target.risk_off in TRADED_UNIVERSE


# --- z-score ---------------------------------------------------------------


def test_trailing_zscore_has_no_look_ahead():
    """The value at t must be reproducible from the series truncated at t.
    This is the single most dangerous bug shape in the module."""
    index = _calendar(400)
    rng = np.random.default_rng(3)
    series = pd.Series(rng.normal(0, 1, len(index)).cumsum(), index=index)
    full = trailing_zscore(series, 60)
    for pos in (100, 250, 399):
        truncated = trailing_zscore(series.iloc[: pos + 1], 60)
        assert truncated.iloc[-1] == pytest.approx(full.iloc[pos])


def test_trailing_zscore_requires_a_full_window():
    index = _calendar(100)
    series = pd.Series(np.arange(100, dtype=float), index=index)
    z = trailing_zscore(series, 60)
    assert z.iloc[:59].isna().all()
    assert pd.notna(z.iloc[59])


def test_trailing_zscore_is_nan_on_zero_variance():
    """A constant series has no scale; the honest answer is 'undefined', not
    an infinity that would become a full-size position."""
    index = _calendar(100)
    series = pd.Series(np.full(100, 5.0), index=index)
    assert trailing_zscore(series, 60).isna().all()


def test_trailing_zscore_matches_manual_computation():
    index = _calendar(80)
    rng = np.random.default_rng(5)
    series = pd.Series(rng.normal(0, 1, 80), index=index)
    z = trailing_zscore(series, 30)
    window = series.iloc[50:80]
    expected = (series.iloc[79] - window.mean()) / window.std(ddof=1)
    assert z.iloc[79] == pytest.approx(expected)


def test_trailing_zscore_rejects_degenerate_window():
    with pytest.raises(ValueError, match="window"):
        trailing_zscore(pd.Series([1.0, 2.0]), 1)


def test_log_ratio_masks_non_positive_prints():
    index = _calendar(5)
    vol = pd.DataFrame({vrt.MOVE: [10.0, 0.0, -1.0, 10.0, 10.0], vrt.VIX: [20.0] * 5}, index=index)
    ratio = vrt._log_ratio(vol, vrt.MOVE, vrt.VIX)
    assert ratio.isna().tolist() == [False, True, True, False, False]


def test_log_ratio_is_nan_when_an_index_is_absent():
    index = _calendar(5)
    vol = pd.DataFrame({vrt.VIX: [20.0] * 5}, index=index)
    assert vrt._log_ratio(vol, vrt.MOVE, vrt.VIX).isna().all()


# --- composite -------------------------------------------------------------


def test_composite_is_the_mean_of_component_zscores():
    index = _calendar(500)
    vol = _noisy_vol_frame(index)
    composite = state_cross_asset_composite(vol, 100)
    components = pd.concat(
        [state_ratio(vol, 100, numerator=t, denominator=vrt.VIX) for t in CROSS_ASSET_COMPONENTS],
        axis=1,
    )
    expected = components.mean(axis=1)
    assert composite.dropna().iloc[-1] == pytest.approx(expected.dropna().iloc[-1])


def test_composite_needs_at_least_two_components():
    """Averaging the z-scores rather than the raw ratios is what makes the
    weights equal in RISK terms; below the minimum count the answer must be
    NaN, not a partial guess."""
    index = _calendar(500)
    vol = _noisy_vol_frame(index)
    # Knock out two of the three components entirely.
    vol[vrt.OVX] = np.nan
    vol[vrt.GVZ] = np.nan
    assert state_cross_asset_composite(vol, 100).isna().all()
    # One knocked out still leaves 2 of 3 -> defined.
    vol2 = _noisy_vol_frame(index)
    vol2[vrt.GVZ] = np.nan
    assert state_cross_asset_composite(vol2, 100).notna().any()
    assert CROSS_ASSET_MIN_COMPONENTS == 2


def test_composite_tracks_gvz_arriving_late():
    """GVZ's real inception is 13 months after the family's formation start;
    the composite must run on MOVE+OVX until GVZ warms rather than idling."""
    index = _calendar(700)
    vol = _noisy_vol_frame(index)
    vol.loc[vol.index[:400], vrt.GVZ] = np.nan
    composite = state_cross_asset_composite(vol, 100)
    assert composite.iloc[150:390].notna().any()


# --- alignment -------------------------------------------------------------


def test_align_uses_the_traded_calendar_and_forward_fills_vol():
    index = _calendar(300)
    traded = _traded_frame(index)
    vol = _flat_vol_frame(index)
    vol.loc[vol.index[100], vrt.MOVE] = np.nan
    vol.loc[vol.index[101], vrt.MOVE] = np.nan
    data = align_vol_regime_data(vol, traded)
    assert data.vol_close.index.equals(data.traded_close.index)
    # Carried forward from day 99, which is OLDER information — never future.
    assert data.vol_close[vrt.MOVE].iloc[100] == pytest.approx(vol[vrt.MOVE].iloc[99])


def test_align_stops_forward_filling_past_the_limit():
    index = _calendar(300)
    traded = _traded_frame(index)
    vol = _flat_vol_frame(index)
    gap = slice(100, 100 + VOL_INDEX_FFILL_LIMIT_DAYS + 3)
    vol.iloc[gap, vol.columns.get_loc(vrt.MOVE)] = np.nan
    data = align_vol_regime_data(vol, traded)
    filled = data.vol_close[vrt.MOVE]
    assert filled.iloc[100 + VOL_INDEX_FFILL_LIMIT_DAYS - 1] == pytest.approx(20.0)
    assert pd.isna(filled.iloc[100 + VOL_INDEX_FFILL_LIMIT_DAYS])


def test_align_drops_days_where_a_traded_leg_did_not_print():
    """A spread cannot be held on a day one of its legs did not trade."""
    index = _calendar(300)
    traded = _traded_frame(index)
    traded.loc[traded.index[50], "IEF"] = np.nan
    data = align_vol_regime_data(_flat_vol_frame(index), traded)
    assert index[50] not in data.traded_close.index
    assert len(data.traded_close) == 299


def test_vol_regime_data_rejects_misaligned_frames():
    index = _calendar(100)
    with pytest.raises(ValueError, match="identical index"):
        VolRegimeData(
            vol_close=_flat_vol_frame(index),
            traded_close=_traded_frame(_calendar(90)),
        )


# --- non-overlapping formation discipline ---------------------------------


@pytest.mark.parametrize("holding", VOL_REGIME_HOLDING_DAYS)
def test_formations_are_non_overlapping_and_adjacent(holding):
    """Amendment 2's core requirement: cadence == holding_days, so every
    realized day belongs to exactly one hold and n_formations is a true count
    of independent bets."""
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    spec = _spec(holding_days=holding)
    result = run_timing_backtest(data, spec, _config())
    assert result.status == "ok"

    active = [f for f in result.formations if f.skipped_reason is None]
    assert len(active) >= 2
    positions = [data.traded_close.index.get_loc(pd.Timestamp(f.formation_date)) for f in active]
    gaps = np.diff(positions)
    assert set(gaps.tolist()) == {holding}


@pytest.mark.parametrize("holding", VOL_REGIME_HOLDING_DAYS)
def test_no_realized_day_is_counted_twice(holding):
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    result = run_timing_backtest(data, _spec(holding_days=holding), _config())
    assert result.daily_returns.index.is_unique
    assert result.daily_returns.index.is_monotonic_increasing


@pytest.mark.parametrize("holding", VOL_REGIME_HOLDING_DAYS)
def test_each_full_hold_contributes_exactly_holding_days_of_returns(holding):
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    result = run_timing_backtest(data, _spec(holding_days=holding), _config())
    active = [f for f in result.formations if f.skipped_reason is None]
    # Every hold but possibly the last (truncated at the end of the sample)
    # contributes exactly `holding` days.
    assert len(result.daily_returns) <= len(active) * holding
    assert len(result.daily_returns) > (len(active) - 1) * holding - 1


@pytest.mark.parametrize("holding", VOL_REGIME_HOLDING_DAYS)
def test_position_is_constant_within_a_hold(holding):
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    result = run_timing_backtest(data, _spec(holding_days=holding), _config())
    active = [f for f in result.formations if f.skipped_reason is None]
    for formation in active[:-1]:
        start = pd.Timestamp(formation.formation_date)
        held = result.positions[
            (result.positions.index > start)
            & (result.positions.index <= start + pd.Timedelta(days=holding * 3))
        ].iloc[:holding]
        assert held.nunique() == 1
        assert held.iloc[0] == pytest.approx(formation.position)


def test_returns_start_the_day_after_formation_never_on_it():
    """Formation is at the close, so the first return a position earns is the
    NEXT day's. A return on the formation day itself would be look-ahead."""
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    result = run_timing_backtest(data, _spec(holding_days=21), _config())
    active = [f for f in result.formations if f.skipped_reason is None]
    first_formation = pd.Timestamp(active[0].formation_date)
    assert result.daily_returns.index[0] > first_formation


def test_future_data_cannot_change_past_positions():
    """End-to-end look-ahead check: scrambling the tail of the vol data must
    leave every position established before that point untouched."""
    index = _calendar()
    traded = _traded_frame(index)
    vol = _noisy_vol_frame(index)
    spec = _spec(holding_days=21)

    baseline = run_timing_backtest(_data(vol, traded), spec, _config())

    tampered = vol.copy()
    cut = 1000
    rng = np.random.default_rng(99)
    tampered.iloc[cut:] = tampered.iloc[cut:] * rng.uniform(0.3, 3.0, tampered.iloc[cut:].shape)
    after = run_timing_backtest(_data(tampered, traded), spec, _config())

    cut_date = index[cut]
    base_early = [f for f in baseline.formations if pd.Timestamp(f.formation_date) < cut_date]
    after_early = [f for f in after.formations if pd.Timestamp(f.formation_date) < cut_date]
    assert len(base_early) == len(after_early) >= 3
    for a, b in zip(base_early, after_early, strict=True):
        assert a.formation_date == b.formation_date
        assert a.position == pytest.approx(b.position)


# --- signal recovery -------------------------------------------------------


def test_a_perfectly_predictive_state_produces_a_strongly_positive_sharpe():
    """If the machinery cannot recover an edge that is genuinely present, a
    zero result from it means nothing. Builds a spread whose next-hold return
    is set by the sign the pre-declared direction implies."""
    index = _calendar(1600)
    rng = np.random.default_rng(21)
    holding = 21

    # A slow oscillating state, z-scored later by the module itself.
    raw = pd.Series(np.sin(np.arange(len(index)) * 2 * np.pi / 210), index=index)
    vol = _flat_vol_frame(index)
    vol[vrt.MOVE] = 20.0 * np.exp(raw * 0.3)
    vol[vrt.VIX] = 20.0

    # Spread return over each hold follows -sign(raw at formation), which is
    # exactly what direction=-1 will bet on.
    spread_daily = np.zeros(len(index))
    for p in range(0, len(index) - holding, holding):
        target_sign = -np.sign(raw.iloc[p])
        spread_daily[p + 1 : p + 1 + holding] = target_sign * 0.0016 + rng.normal(
            0, 0.0025, holding
        )

    ief = pd.Series(100.0, index=index)
    spy = pd.Series(100.0 * np.exp(np.cumsum(spread_daily)), index=index)
    traded = pd.DataFrame({"SPY": spy, "IEF": ief, "HYG": spy}, index=index)

    result = run_timing_backtest(_data(vol, traded), _spec(holding_days=holding), _config())
    assert result.status == "ok"
    from app.services.research_lab.metrics import sharpe_ratio

    assert sharpe_ratio(result.daily_returns) > 1.0


def test_a_pure_noise_state_produces_a_near_zero_or_negative_sharpe():
    index = _calendar()
    data = _data(_noisy_vol_frame(index, seed=404), _traded_frame(index, seed=505))
    result = run_timing_backtest(data, _spec(holding_days=21), _config())
    from app.services.research_lab.metrics import sharpe_ratio

    assert abs(sharpe_ratio(result.daily_returns)) < 1.5


# --- cost and financing accounting ----------------------------------------


def test_turnover_cost_is_two_legs_of_the_position_change():
    """A unit spread trades gross notional 2.0 (one unit long, one short), so
    a position change of |dw| costs cost_bps * 2 * |dw|."""
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    config = _config(cost_bps=10.0)
    result = run_timing_backtest(data, _spec(holding_days=21), config)
    for formation in result.formations:
        assert formation.cost == pytest.approx(10.0 / 1e4 * 2.0 * formation.turnover)


def test_total_cost_is_the_sum_of_formation_costs():
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    result = run_timing_backtest(data, _spec(holding_days=21), _config())
    assert result.total_cost == pytest.approx(sum(f.cost for f in result.formations))


def test_zero_cost_config_leaves_returns_gross_of_turnover():
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    spec = _spec(holding_days=21)
    costed = run_timing_backtest(data, spec, _config(cost_bps=50.0, short_borrow_bps_per_year=0.0))
    free = run_timing_backtest(data, spec, _config(cost_bps=0.0, short_borrow_bps_per_year=0.0))
    assert free.total_cost == 0.0
    assert costed.total_cost > 0.0
    assert free.daily_returns.sum() > costed.daily_returns.sum()


def test_higher_cost_monotonically_reduces_net_return():
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    spec = _spec(holding_days=21)
    sums = [
        run_timing_backtest(
            data, spec, _config(cost_bps=bps, short_borrow_bps_per_year=0.0)
        ).daily_returns.sum()
        for bps in (0.0, 5.0, 20.0)
    ]
    assert sums[0] > sums[1] > sums[2]


def test_shorter_holds_pay_more_turnover_cost():
    """The standing lesson from every family screened here: reformation cost
    scales with rebalance frequency."""
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    costs = [
        run_timing_backtest(data, _spec(holding_days=h), _config()).total_cost
        for h in (21, 63)
    ]
    assert costs[0] > costs[1]


def test_financing_accrues_on_calendar_days_so_a_weekend_costs_three():
    """Charging per TRADING day would undercharge a continuously held book by
    ~31%, the wrong direction for a cost."""
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    spec = _spec(holding_days=21)
    result = run_timing_backtest(
        data, spec, _config(cost_bps=0.0, short_borrow_bps_per_year=365.0)
    )
    gross_spec_result = run_timing_backtest(
        data, spec, _config(cost_bps=0.0, short_borrow_bps_per_year=0.0)
    )
    charged = gross_spec_result.daily_returns - result.daily_returns

    dates = result.daily_returns.index
    elapsed = pd.Series(dates, index=dates).diff().dt.days
    mondays = elapsed[elapsed == 3].index
    tuesdays = elapsed[elapsed == 1].index
    assert len(mondays) > 5 and len(tuesdays) > 5
    # Same |position| scale on both, so the ratio of average charge is ~3.
    ratio = charged.loc[mondays].mean() / charged.loc[tuesdays].mean()
    assert 2.0 < ratio < 4.0


def test_financing_scales_with_absolute_position_only():
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    spec = _spec(holding_days=21)
    low = run_timing_backtest(data, spec, _config(short_borrow_bps_per_year=10.0))
    high = run_timing_backtest(data, spec, _config(short_borrow_bps_per_year=100.0))
    assert high.total_financing_cost == pytest.approx(low.total_financing_cost * 10.0, rel=1e-6)


def test_financing_and_turnover_are_reported_separately():
    """cross_sectional.py's two-cost convention: they push in opposite
    directions across the holding_days axis, so one blended number cannot
    represent both."""
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    short_hold = run_timing_backtest(data, _spec(holding_days=21), _config())
    long_hold = run_timing_backtest(data, _spec(holding_days=63), _config())
    assert short_hold.total_cost > long_hold.total_cost
    assert short_hold.total_financing_cost > 0
    assert long_hold.total_financing_cost > 0


# --- skipped formations ----------------------------------------------------


def test_uncomputable_state_skips_the_hold_instead_of_recording_zeros():
    """Forced zeros would shrink both mean and std and report the Sharpe of
    'hold cash for a year, then trade' as the Sharpe of the signal."""
    index = _calendar()
    traded = _traded_frame(index)
    vol = _noisy_vol_frame(index)
    # MOVE unavailable for the first 600 days -> move_vix uncomputable there.
    vol.loc[vol.index[:600], vrt.MOVE] = np.nan
    data = _data(vol, traded)
    result = run_timing_backtest(data, _spec(holding_days=21), _config())

    assert result.n_skipped_formations > 0
    assert (result.daily_returns == 0.0).sum() == 0
    assert result.daily_returns.index[0] > index[600]


def test_leading_warmup_skips_are_not_counted_as_interior_skips():
    index = _calendar()
    vol = _noisy_vol_frame(index)
    vol.loc[vol.index[:600], vrt.MOVE] = np.nan
    result = run_timing_backtest(
        _data(vol, _traded_frame(index)), _spec(holding_days=21), _config()
    )
    assert result.n_skipped_formations > 0
    assert result.n_interior_skips == 0


def test_an_index_dying_mid_sample_is_counted_as_an_interior_skip(caplog):
    index = _calendar()
    vol = _noisy_vol_frame(index)
    vol.loc[vol.index[1100:], vrt.MOVE] = np.nan
    with caplog.at_level("WARNING"):
        result = run_timing_backtest(
            _data(vol, _traded_frame(index)), _spec(holding_days=21), _config()
        )
    assert result.n_interior_skips > 0
    assert "INTERIOR skipped formation" in caplog.text


def test_closing_a_position_into_a_skip_still_costs():
    """Going flat is a real trade and must be charged; only flat-to-flat is
    free."""
    index = _calendar()
    vol = _noisy_vol_frame(index)
    vol.loc[vol.index[900:], vrt.MOVE] = np.nan
    result = run_timing_backtest(
        _data(vol, _traded_frame(index)), _spec(holding_days=21), _config()
    )
    skips = [f for f in result.formations if f.skipped_reason is not None]
    assert any(f.cost > 0 for f in skips)
    assert all(f.position == 0.0 for f in skips)
    # Successive skips after the book is already flat cost nothing.
    assert any(f.cost == 0.0 for f in skips)


def test_missing_traded_instrument_is_reported_not_silently_empty():
    index = _calendar()
    traded = _traded_frame(index).drop(columns=["IEF"])
    data = align_vol_regime_data(_noisy_vol_frame(index), traded)
    result = run_timing_backtest(data, _spec(holding_days=21), _config())
    assert result.status == "missing_traded_instrument"
    assert len(result.daily_returns) == 0


def test_start_after_all_history_yields_a_named_status():
    index = _calendar(300)
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    result = run_timing_backtest(
        data, _spec(holding_days=21), _config(formation_start=date(2099, 1, 1))
    )
    assert result.status == "no_history_after_start"


# --- position sizing -------------------------------------------------------


def test_position_is_clipped_to_unit_leverage():
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    result = run_timing_backtest(data, _spec(holding_days=21), _config())
    assert result.positions.abs().max() <= 1.0
    for formation in result.formations:
        assert -1.0 <= formation.position <= 1.0


def test_position_sign_follows_the_pre_declared_direction():
    """direction=-1 means a HIGH state z (rich implied vol) must produce a
    SHORT risk-on position."""
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    spec = _spec(holding_days=21)
    result = run_timing_backtest(data, spec, _config())
    active = [f for f in result.formations if f.skipped_reason is None and abs(f.state_z) > 0.05]
    assert len(active) > 5
    for formation in active:
        assert np.sign(formation.position) == np.sign(VOL_REGIME_DIRECTION * formation.state_z)


# --- confound diagnostics --------------------------------------------------


def test_a_pure_static_tilt_is_exposed_by_a_near_zero_residual_sharpe():
    """THE test that matters. A constant position in the target spread must
    show a high spread_beta and a residual Sharpe collapsing toward zero —
    the same regression that reduced this project's commodities family from a
    0.767 DSR to a residual Sharpe of ~0.000."""
    index = _calendar(1600)
    # A state pinned far to one side, so the z-score never changes sign and
    # the "timing" signal is really a constant position.
    vol = _flat_vol_frame(index)
    ramp = np.linspace(0.0, 1.0, len(index))
    vol[vrt.MOVE] = 20.0 * np.exp(ramp)
    vol[vrt.VIX] = 20.0

    rng = np.random.default_rng(31)
    spread_daily = rng.normal(0.0007, 0.006, len(index))
    ief = pd.Series(100.0, index=index)
    spy = pd.Series(100.0 * np.exp(np.cumsum(spread_daily)), index=index)
    traded = pd.DataFrame({"SPY": spy, "IEF": ief, "HYG": spy}, index=index)

    data = _data(vol, traded)
    spec = _spec(holding_days=21)
    replay = run_timing_backtest(data, spec, _config())
    diag = compute_confound_diagnostics(spec, replay, data.traded_close)

    from app.services.research_lab.metrics import sharpe_ratio

    raw = sharpe_ratio(replay.daily_returns)
    # The beta absorbs essentially the whole position...
    assert abs(diag.spread_beta) > 0.5
    assert abs(diag.mean_position) > 0.5
    # ...leaving no positive alpha behind. Compared SIGNED, not on abs():
    # with a near-constant position the hedge is near-perfect and all that
    # remains is the cost drag, a near-deterministic small negative whose
    # Sharpe is large in magnitude and firmly negative.
    assert diag.residual_sharpe < 0.5 * abs(raw)
    assert diag.spread_alpha_annualized < 0.0


def test_a_genuine_timing_signal_keeps_its_residual_sharpe():
    """The mirror of the test above — the diagnostic must not condemn a real
    signal, or it would be useless."""
    index = _calendar(1600)
    rng = np.random.default_rng(41)
    holding = 21
    raw = pd.Series(np.sin(np.arange(len(index)) * 2 * np.pi / 210), index=index)
    vol = _flat_vol_frame(index)
    vol[vrt.MOVE] = 20.0 * np.exp(raw * 0.3)
    vol[vrt.VIX] = 20.0

    spread_daily = np.zeros(len(index))
    for p in range(0, len(index) - holding, holding):
        spread_daily[p + 1 : p + 1 + holding] = -np.sign(raw.iloc[p]) * 0.0016 + rng.normal(
            0, 0.0025, holding
        )
    ief = pd.Series(100.0, index=index)
    spy = pd.Series(100.0 * np.exp(np.cumsum(spread_daily)), index=index)
    traded = pd.DataFrame({"SPY": spy, "IEF": ief, "HYG": spy}, index=index)

    data = _data(vol, traded)
    spec = _spec(holding_days=holding)
    replay = run_timing_backtest(data, spec, _config())
    diag = compute_confound_diagnostics(spec, replay, data.traded_close)
    assert diag.residual_sharpe > 1.0
    assert abs(diag.mean_position) < 0.4


def test_residual_sharpe_is_beta_hedged_not_the_intercept_removed_residual():
    """REGRESSION TEST for a bug that made the whole confound check vacuous.

    An OLS residual series computed WITH the intercept (y - alpha - beta*x)
    has mean exactly zero by construction, so its Sharpe is ~0 for every
    strategy — which reads as 'every spec is a disguised static tilt' with
    total confidence. The reported number must instead be the Sharpe of the
    beta-hedged stream y - beta*x, whose mean is the alpha."""
    index = _calendar(1600)
    rng = np.random.default_rng(41)
    holding = 21
    raw = pd.Series(np.sin(np.arange(len(index)) * 2 * np.pi / 210), index=index)
    vol = _flat_vol_frame(index)
    vol[vrt.MOVE] = 20.0 * np.exp(raw * 0.3)
    vol[vrt.VIX] = 20.0
    spread_daily = np.zeros(len(index))
    for p in range(0, len(index) - holding, holding):
        spread_daily[p + 1 : p + 1 + holding] = -np.sign(raw.iloc[p]) * 0.0016 + rng.normal(
            0, 0.0025, holding
        )
    traded = pd.DataFrame(
        {
            "SPY": pd.Series(100.0 * np.exp(np.cumsum(spread_daily)), index=index),
            "IEF": pd.Series(100.0, index=index),
            "HYG": pd.Series(100.0 * np.exp(np.cumsum(spread_daily)), index=index),
        },
        index=index,
    )
    data = _data(vol, traded)
    spec = _spec(holding_days=holding)
    replay = run_timing_backtest(data, spec, _config())
    diag = compute_confound_diagnostics(spec, replay, data.traded_close)

    from app.services.research_lab.metrics import sharpe_ratio

    aligned = pd.concat(
        [replay.daily_returns.rename("y"), replay.spread_returns.rename("x")], axis=1
    ).dropna()
    beta_hedged = aligned["y"] - diag.spread_beta * aligned["x"]
    intercept_removed = beta_hedged - beta_hedged.mean()

    assert diag.residual_sharpe == pytest.approx(sharpe_ratio(beta_hedged))
    # The buggy definition is always ~0; the correct one here is not.
    assert abs(sharpe_ratio(intercept_removed)) < 1e-9
    assert abs(diag.residual_sharpe) > 1.0
    # alpha and the hedged stream describe the same thing.
    assert diag.spread_alpha_annualized == pytest.approx(
        beta_hedged.mean() * 252, rel=1e-6
    )


def test_ols_beta_alpha_recovers_a_known_slope():
    index = _calendar(500)
    rng = np.random.default_rng(13)
    x = pd.Series(rng.normal(0, 0.01, len(index)), index=index)
    y = 0.35 + 1.7 * x
    beta, alpha = vrt._ols_beta_alpha(y, x)
    assert beta == pytest.approx(1.7, rel=1e-6)
    assert alpha == pytest.approx(0.35, rel=1e-6)


def test_ols_beta_alpha_handles_a_constant_regressor():
    """The honest degenerate answer is 'nothing to explain y with', not a NaN
    that would silently poison the residual Sharpe."""
    index = _calendar(100)
    x = pd.Series(np.full(100, 0.5), index=index)
    y = pd.Series(np.arange(100, dtype=float), index=index)
    beta, alpha = vrt._ols_beta_alpha(y, x)
    assert beta == 0.0
    assert alpha == pytest.approx(y.mean())


def test_ols_beta_alpha_handles_too_few_points():
    s = pd.Series([1.0, 2.0])
    assert vrt._ols_beta_alpha(s, s) == (0.0, 0.0)


def test_subperiod_sharpes_split_the_sample_into_thirds():
    index = _calendar(900)
    rng = np.random.default_rng(17)
    returns = pd.Series(rng.normal(0, 0.01, len(index)), index=index)
    thirds = vrt._subperiod_sharpes(returns)
    assert len(thirds) == 3
    assert all(np.isfinite(s) for s in thirds)


def test_subperiod_sharpes_expose_one_crisis_dependence():
    """A signal that earns everything in one window must not look uniform."""
    index = _calendar(900)
    rng = np.random.default_rng(19)
    values = rng.normal(0, 0.004, len(index))
    values[:300] += 0.006  # all the edge lives in the first third
    thirds = vrt._subperiod_sharpes(pd.Series(values, index=index))
    assert thirds[0] > 2.0
    assert max(thirds[1], thirds[2]) < 1.0


def test_confound_diagnostics_are_computed_for_every_screened_spec():
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    results = screen_vol_regime_timing(data, VOL_REGIME_FAMILY[:6], _config())
    assert results
    for result in results:
        assert result.confound.spec_id == result.spec_id
        assert np.isfinite(result.confound.spread_beta)
        assert np.isfinite(result.confound.residual_sharpe)
        assert np.isfinite(result.confound.equity_beta)
        assert np.isfinite(result.confound.rates_beta)


# --- block bootstrap -------------------------------------------------------


def test_block_bootstrap_returns_a_valid_probability():
    index = _calendar(900)
    rng = np.random.default_rng(23)
    returns = pd.Series(rng.normal(0.0003, 0.01, len(index)), index=index)
    p = block_bootstrap_sharpe_pvalue(returns, 21, n_resamples=500)
    assert p is not None
    assert 0.0 < p <= 1.0


def test_block_bootstrap_is_deterministic_for_a_fixed_seed():
    index = _calendar(900)
    rng = np.random.default_rng(29)
    returns = pd.Series(rng.normal(0.0002, 0.01, len(index)), index=index)
    a = block_bootstrap_sharpe_pvalue(returns, 21, n_resamples=400)
    b = block_bootstrap_sharpe_pvalue(returns, 21, n_resamples=400)
    assert a == b


def test_block_bootstrap_does_not_reject_a_zero_edge_series():
    index = _calendar(1200)
    rng = np.random.default_rng(37)
    returns = pd.Series(rng.normal(0.0, 0.01, len(index)), index=index)
    p = block_bootstrap_sharpe_pvalue(returns, 21, n_resamples=800)
    assert p > 0.05


def test_block_bootstrap_rejects_a_large_genuine_edge():
    index = _calendar(1200)
    rng = np.random.default_rng(43)
    returns = pd.Series(rng.normal(0.0025, 0.005, len(index)), index=index)
    p = block_bootstrap_sharpe_pvalue(returns, 21, n_resamples=800)
    assert p < 0.05


def test_block_bootstrap_declines_when_there_are_too_few_blocks():
    """With fewer than MIN_FORMATIONS_FOR_BOOTSTRAP distinct blocks the null
    distribution is built from too few independent pieces to mean anything."""
    index = _calendar(120)
    rng = np.random.default_rng(47)
    returns = pd.Series(rng.normal(0, 0.01, len(index)), index=index)
    assert block_bootstrap_sharpe_pvalue(returns, 63, n_resamples=200) is None


def test_block_bootstrap_declines_on_a_series_below_the_replay_floor():
    index = _calendar(40)
    returns = pd.Series(np.random.default_rng(51).normal(0, 0.01, 40), index=index)
    assert block_bootstrap_sharpe_pvalue(returns, 5, n_resamples=200) is None


def test_block_bootstrap_preserves_serial_dependence():
    """A strongly autocorrelated series must yield a WIDER null (and so a
    larger p-value) under block resampling than under iid resampling — that
    difference is the whole reason the bootstrap is blocked."""
    index = _calendar(1200)
    rng = np.random.default_rng(53)
    shocks = rng.normal(0, 0.01, len(index))
    smoothed = pd.Series(shocks).rolling(60, min_periods=1).mean().to_numpy()
    # A MODEST edge on purpose: with a large one both p-values pin to the
    # 1/(n_resamples+1) floor and the comparison cannot discriminate.
    autocorrelated = pd.Series(smoothed + 0.00012, index=index)
    blocked = block_bootstrap_sharpe_pvalue(autocorrelated, 63, n_resamples=2000)
    iid = block_bootstrap_sharpe_pvalue(autocorrelated, 1, n_resamples=2000)
    assert blocked is not None and iid is not None
    assert blocked > iid
    assert blocked > 1.0 / 2001


# --- screening -------------------------------------------------------------


def test_n_trials_is_the_declared_family_size_not_the_survivor_count():
    """Shrinking the denominator to 'specs that worked' would be gameable by
    declaring specs expected to fail."""
    index = _calendar()
    vol = _noisy_vol_frame(index)
    # Kill GVZ so its specs cannot replay at all.
    vol[vrt.GVZ] = np.nan
    data = _data(vol, _traded_frame(index))
    specs = VOL_REGIME_FAMILY
    results = screen_vol_regime_timing(data, specs, _config())
    assert len(results) < len(specs)
    for result in results:
        assert result.deflated_sharpe.n_trials == len(specs) == VOL_REGIME_N_TRIALS


def test_sigma_sr_is_the_sibling_sharpe_dispersion():
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    results = screen_vol_regime_timing(data, VOL_REGIME_FAMILY, _config())
    assert len(results) >= 2
    expected = float(np.std([r.sharpe_annualized for r in results], ddof=1))
    for result in results:
        assert result.deflated_sharpe.sigma_sr_annualized == pytest.approx(expected)


def test_results_are_sorted_by_sharpe_descending():
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    results = screen_vol_regime_timing(data, VOL_REGIME_FAMILY, _config())
    sharpes = [r.sharpe_annualized for r in results]
    assert sharpes == sorted(sharpes, reverse=True)


def test_specs_below_the_replay_floor_are_dropped():
    index = _calendar(400)  # 252 warmup leaves well under the 60-day floor
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    results = screen_vol_regime_timing(data, VOL_REGIME_FAMILY, _config())
    for result in results:
        assert result.n_trading_days >= MIN_REPLAY_TRADING_DAYS


def test_screening_reports_every_declared_field():
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    results = screen_vol_regime_timing(data, VOL_REGIME_FAMILY[:4], _config())
    assert results
    for result in results:
        assert result.state_key
        assert result.target_key in {"spy_ief", "hyg_ief"}
        assert result.holding_days in VOL_REGIME_HOLDING_DAYS
        assert result.n_formations > 0
        assert result.first_formation is not None
        assert result.last_formation is not None
        assert result.first_formation <= result.last_formation
        assert np.isfinite(result.net_cumulative_return)
        assert result.total_cost_drag >= 0
        assert result.total_financing_drag >= 0


def test_net_cumulative_return_plus_charges_reconstructs_the_pre_cost_return():
    """The additivity the breakeven-cost arithmetic depends on."""
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    spec = VOL_REGIME_FAMILY[0]
    config = _config()
    costed = screen_vol_regime_timing(data, [spec], config)[0]
    free = run_timing_backtest(
        data, spec, _config(cost_bps=0.0, short_borrow_bps_per_year=0.0)
    )
    reconstructed = costed.net_cumulative_return + costed.total_cost_drag + costed.total_financing_drag
    assert reconstructed == pytest.approx(float(free.daily_returns.sum()), abs=1e-9)


def test_empty_spec_list_returns_no_results():
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    assert screen_vol_regime_timing(data, [], _config()) == []


# --- disclosure ------------------------------------------------------------


def test_disclosure_states_the_uncounted_prior_search():
    """The correction that sank this project's buyback family — it must be
    impossible to read these results without it."""
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    results = screen_vol_regime_timing(data, VOL_REGIME_FAMILY, _config())
    lines = build_vol_regime_disclosure(results, _config())
    joined = " ".join(lines)
    assert "upper bound" in joined
    assert "NOT in the denominator" in joined
    assert "48" in joined


def test_disclosure_states_costs_direction_and_overlap_discipline():
    index = _calendar()
    data = _data(_noisy_vol_frame(index), _traded_frame(index))
    results = screen_vol_regime_timing(data, VOL_REGIME_FAMILY, _config())
    joined = " ".join(build_vol_regime_disclosure(results, _config()))
    assert "non-overlapping" in joined
    assert "block bootstrap" in joined
    assert "borrow" in joined
    assert "never fitted per spec" in joined


def test_static_tilt_detector_uses_a_signed_not_absolute_comparison():
    """REGRESSION TEST. With a near-constant position the hedge is
    near-perfect, only the cost drag remains, and its Sharpe is a large
    NEGATIVE number. An abs()-based threshold would clear the most blatant
    possible static tilt precisely because its residual Sharpe is enormous."""

    class _Stub:
        def __init__(self, sharpe, residual):
            self.sharpe_annualized = sharpe
            self.spec_id = "stub"
            self.total_cost_drag = 0.01
            self.total_financing_drag = 0.01
            self.net_cumulative_return = 0.1
            self.n_trading_days = 500
            self.n_formations = 20
            self.confound = type("C", (), {"residual_sharpe": residual})()

    blatant = _Stub(sharpe=1.2, residual=-20.0)
    genuine = _Stub(sharpe=1.2, residual=1.1)
    assert "static tilt" in " ".join(build_vol_regime_disclosure([blatant], _config()))
    assert "static tilt" not in " ".join(build_vol_regime_disclosure([genuine], _config()))


def test_disclosure_survives_an_empty_result_set():
    lines = build_vol_regime_disclosure([], _config())
    assert any("nothing to interpret" in line for line in lines)


def test_disclosure_flags_disguised_static_tilts():
    index = _calendar(1600)
    vol = _flat_vol_frame(index)
    vol[vrt.MOVE] = 20.0 * np.exp(np.linspace(0.0, 1.0, len(index)))
    vol[vrt.VIX] = 20.0
    rng = np.random.default_rng(59)
    spy = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0.0007, 0.006, len(index)))), index=index)
    traded = pd.DataFrame(
        {"SPY": spy, "IEF": pd.Series(100.0, index=index), "HYG": spy}, index=index
    )
    data = _data(vol, traded)
    specs = [s for s in VOL_REGIME_FAMILY if s.state_key == "move_vix"]
    results = screen_vol_regime_timing(data, specs, _config())
    joined = " ".join(build_vol_regime_disclosure(results, _config()))
    if any(r.sharpe_annualized > 0 for r in results):
        assert "static tilt" in joined


# --- production entry point ------------------------------------------------


class _FakeProvider:
    """Mirrors YFinanceProvider.get_price_history's contract only."""

    def __init__(self, vol: pd.DataFrame, traded: pd.DataFrame, missing=None):
        self._vol = vol
        self._traded = traded
        self._missing = missing or []
        self.calls: list[list[str]] = []

    def get_price_history(self, tickers, start, end):
        self.calls.append(list(tickers))
        if set(tickers) & set(VOL_INDEX_UNIVERSE):
            frame = self._vol
        else:
            frame = self._traded
        present = [t for t in tickers if t in frame.columns]
        return frame[present], [t for t in tickers if t not in frame.columns]


def test_run_screening_end_to_end_with_a_fake_provider():
    index = _calendar()
    provider = _FakeProvider(_noisy_vol_frame(index), _traded_frame(index))
    summary = run_vol_regime_screening(
        start=date(2010, 1, 4), end=date(2015, 6, 1), provider=provider
    )
    assert summary.results
    assert summary.disclosure
    assert summary.formation_calendar_start is not None
    assert summary.formation_calendar_end is not None
    assert set(summary.vol_index_starts) <= set(VOL_INDEX_UNIVERSE)
    for result in summary.results:
        assert result.deflated_sharpe.n_trials == VOL_REGIME_N_TRIALS


def test_run_screening_pads_history_before_the_formation_start():
    """The 252-day z-window must be warm at the first formation, so the fetch
    has to begin well before it."""
    index = _calendar()
    provider = _FakeProvider(_noisy_vol_frame(index), _traded_frame(index))
    run_vol_regime_screening(start=date(2012, 1, 3), end=date(2015, 6, 1), provider=provider)
    assert provider.calls


def test_run_screening_reports_missing_vol_indices(caplog):
    index = _calendar()
    vol = _noisy_vol_frame(index).drop(columns=[vrt.GVZ])
    provider = _FakeProvider(vol, _traded_frame(index))
    with caplog.at_level("ERROR"):
        summary = run_vol_regime_screening(
            start=date(2010, 1, 4), end=date(2015, 6, 1), provider=provider
        )
    assert vrt.GVZ in summary.missing_vol_indices
    assert "resolved NO price data" in caplog.text


def test_run_screening_handles_an_empty_fetch():
    empty = pd.DataFrame()
    provider = _FakeProvider(empty, empty)
    summary = run_vol_regime_screening(
        start=date(2010, 1, 4), end=date(2015, 6, 1), provider=provider
    )
    assert summary.results == []


def test_default_config_is_a_fresh_object_each_call():
    """Callers must not be able to mutate shared family configuration."""
    a = default_vol_regime_config()
    b = default_vol_regime_config()
    assert a is not b
    a.cost_bps = 999.0
    assert b.cost_bps == VOL_REGIME_COST_BPS


def test_declared_costs_are_the_documented_values():
    config = default_vol_regime_config()
    assert config.cost_bps == VOL_REGIME_COST_BPS == 2.0
    assert config.short_borrow_bps_per_year == 50.0
