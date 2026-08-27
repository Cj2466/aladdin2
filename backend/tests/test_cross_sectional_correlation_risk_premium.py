"""Tests for the Correlation-Risk-Premium family.

Synthetic fixtures are seed-verified and deterministic — no test here touches
the network except the one explicitly gated behind ALADDIN_LIVE_DATA_TESTS,
following conftest.py's canned_prices convention ("tests must never depend on
live yfinance data").
"""

import os
from datetime import date

import httpx
import numpy as np
import pandas as pd
import pytest

import app.services.research_lab.cross_sectional_correlation_risk_premium as crp_mod
from app.services.research_lab.cross_sectional_correlation_risk_premium import (
    CBOE_FFILL_LIMIT_DAYS,
    CBOE_VERIFIED_START,
    COR1M,
    COR3M,
    CRP_DIRECTION,
    CRP_FAMILY,
    CRP_HOLDING_DAYS,
    CRP_N_TRIALS,
    CRP_VIX_OVERLAP_THRESHOLD,
    CRP_Z_WINDOW,
    IMPLIED_CORRELATION_INDICES,
    MIN_NAMES_FOR_REALIZED_CORRELATION,
    REALIZED_WINDOW_1M,
    REALIZED_WINDOW_3M,
    SECTOR_ETF_UNIVERSE,
    TRADED_TICKER,
    VIX,
    VIX_CONTROL_KEY,
    CboeDataError,
    CrpConfig,
    CrpData,
    CrpSpec,
    align_crp_data,
    build_crp_disclosure,
    compute_confound_diagnostics,
    compute_overlap_diagnostics,
    compute_pit_realized_correlation_crosscheck,
    correlation_risk_premium,
    default_crp_config,
    fetch_cboe_implied_correlation,
    parse_cboe_history_csv,
    rolling_average_pairwise_correlation,
    run_crp_backtest,
    run_crp_screening,
    screen_crp_timing,
    state_crp,
    state_vix_level,
)
from app.services.research_lab.deflated_sharpe import MIN_TRIALS_FOR_DSR
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.vol_regime_timing import MIN_REPLAY_TRADING_DAYS

# --- synthetic-data helpers -----------------------------------------------

# Long enough for the 63-day realized window plus the 252-day z warmup on top
# of it, plus a comfortable number of non-overlapping 63-day holds.
_N_DAYS = 1500
_START = "2010-01-04"


def _calendar(n: int = _N_DAYS) -> pd.DatetimeIndex:
    return pd.bdate_range(_START, periods=n)


def _sector_frame(index: pd.DatetimeIndex, seed: int = 11) -> pd.DataFrame:
    """Nine correlated sector price series: a shared market factor plus an
    idiosyncratic component, so their average pairwise correlation is a
    genuine number in (0, 1) rather than 1.0 or noise."""
    rng = np.random.default_rng(seed)
    market = rng.normal(0.0, 0.01, len(index))
    columns = {}
    for i, ticker in enumerate(SECTOR_ETF_UNIVERSE):
        idio = np.random.default_rng(seed + 100 + i).normal(0.0, 0.01, len(index))
        columns[ticker] = 100.0 * np.cumprod(1 + market + idio)
    return pd.DataFrame(columns, index=index)


def _spy(index: pd.DatetimeIndex, seed: int = 7) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(
        400.0 * np.cumprod(1 + rng.normal(0.0002, 0.011, len(index))),
        index=index,
        name=TRADED_TICKER,
    )


def _vix(index: pd.DatetimeIndex, seed: int = 3) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(
        20.0 * np.exp(pd.Series(rng.normal(0, 0.05, len(index))).cumsum().to_numpy() * 0.1),
        index=index,
        name=VIX,
    )


def _implied_frame(index: pd.DatetimeIndex, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = 35.0 + pd.Series(rng.normal(0, 0.4, len(index))).cumsum().to_numpy() * 0.1
    base = np.clip(base, 5.0, 95.0)
    return pd.DataFrame({COR1M: base, COR3M: base + 4.0}, index=index)


def _data(
    index: pd.DatetimeIndex | None = None,
    *,
    implied: pd.DataFrame | None = None,
    sectors: pd.DataFrame | None = None,
    vix: pd.Series | None = None,
    spy: pd.Series | None = None,
) -> CrpData:
    index = _calendar() if index is None else index
    return align_crp_data(
        _implied_frame(index) if implied is None else implied,
        _sector_frame(index) if sectors is None else sectors,
        _vix(index) if vix is None else vix,
        _spy(index) if spy is None else spy,
    )


def _config(**overrides) -> CrpConfig:
    config = default_crp_config()
    config.formation_start = date(2011, 1, 3)
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def _spec(state_fn, holding: int = 21, **overrides) -> CrpSpec:
    defaults = {
        "spec_id": "test_spec",
        "state_key": "test",
        "citation": "test",
        "hypothesis": "test",
        "state_fn": state_fn,
        "holding_days": holding,
    }
    defaults.update(overrides)
    return CrpSpec(**defaults)


# --- the pre-declared family ----------------------------------------------


def test_family_is_exactly_the_declared_grid():
    assert len(CRP_FAMILY) == CRP_N_TRIALS == 15
    assert len(CRP_FAMILY) == len(crp_mod._STATE_VARIABLES) * len(CRP_HOLDING_DAYS)


def test_n_trials_clears_the_dsr_floor():
    """Below MIN_TRIALS_FOR_DSR the DSR machinery declines to compute a
    multiple-comparisons benchmark at all, so a family smaller than that
    could not be honestly deflated."""
    assert CRP_N_TRIALS >= MIN_TRIALS_FOR_DSR


def test_family_spec_ids_are_unique():
    assert len({s.spec_id for s in CRP_FAMILY}) == len(CRP_FAMILY)


def test_every_state_holding_cell_appears_exactly_once():
    cells = [(s.state_key, s.holding_days) for s in CRP_FAMILY]
    assert len(set(cells)) == len(cells) == CRP_N_TRIALS


def test_direction_is_uniform_and_never_fitted_per_spec():
    """A per-spec sign would double the real search to 30 while still
    reporting n_trials=15 — the uncounted degree of freedom the DSR exists
    to prevent."""
    assert {s.direction for s in CRP_FAMILY} == {CRP_DIRECTION}
    assert CRP_DIRECTION == 1.0


def test_z_window_is_fixed_not_searched():
    assert {s.z_window for s in CRP_FAMILY} == {CRP_Z_WINDOW}


def test_holding_periods_are_exactly_the_declared_three():
    assert {s.holding_days for s in CRP_FAMILY} == set(CRP_HOLDING_DAYS)


def test_family_build_asserts_on_grid_drift(monkeypatch):
    """A silent drift in family size silently changes the DSR denominator."""
    monkeypatch.setattr(crp_mod, "CRP_HOLDING_DAYS", (5, 21))
    with pytest.raises(AssertionError, match="CRP_N_TRIALS"):
        crp_mod._build_crp_family()


def test_vix_control_exists_at_every_holding_period():
    """The like-for-like comparison against the already-rejected vol-regime
    family. A missing horizon would leave a CRP spec with no counterpart."""
    horizons = {s.holding_days for s in CRP_FAMILY if s.state_key == VIX_CONTROL_KEY}
    assert horizons == set(CRP_HOLDING_DAYS)


def test_both_crp_tenors_and_all_three_controls_are_present():
    keys = {s.state_key for s in CRP_FAMILY}
    assert keys == {"crp_1m", "crp_3m", "implied_1m", "realized_21d", VIX_CONTROL_KEY}
    hypotheses = {s.state_key for s in CRP_FAMILY if s.is_crp_hypothesis}
    assert hypotheses == {"crp_1m", "crp_3m"}


def test_every_spec_carries_a_citation_and_hypothesis():
    for spec in CRP_FAMILY:
        assert len(spec.citation) > 40
        assert len(spec.hypothesis) > 20


def test_realized_windows_are_tenor_matched_to_their_implied_index():
    assert REALIZED_WINDOW_1M == 21
    assert REALIZED_WINDOW_3M == 63


# --- CBOE parsing ----------------------------------------------------------

_CSV = "DATE,OPEN,HIGH,LOW,CLOSE\n01/03/2006,23.5,23.5,23.5,23.5\n01/04/2006,24.33,24.33,24.33,24.33\n"


def test_parse_cboe_reads_close_on_a_date_index():
    series = parse_cboe_history_csv(_CSV, COR1M)
    assert list(series.index) == [pd.Timestamp("2006-01-03"), pd.Timestamp("2006-01-04")]
    assert series.iloc[0] == pytest.approx(23.5)
    assert series.name == COR1M


def test_parse_cboe_uses_the_explicit_us_date_format():
    """An inferred parse would read 03/04/2006 as 4 March in one run and
    3 April in another depending on how many unambiguous rows led the file."""
    series = parse_cboe_history_csv("DATE,CLOSE\n03/04/2006,40.0\n", COR1M)
    assert series.index[0] == pd.Timestamp("2006-03-04")


def test_parse_cboe_tolerates_whitespace_and_case_in_headers():
    series = parse_cboe_history_csv(" date , Close \n01/03/2006,23.5\n", COR1M)
    assert series.iloc[0] == pytest.approx(23.5)


def test_parse_cboe_drops_non_positive_prints():
    """An implied correlation of zero or below is not a real print, and
    leaving one in would produce a garbage z-score downstream."""
    series = parse_cboe_history_csv("DATE,CLOSE\n01/03/2006,23.5\n01/04/2006,0.0\n", COR1M)
    assert len(series) == 1
    assert series.iloc[0] == pytest.approx(23.5)


def test_parse_cboe_rejects_a_changed_feed_shape():
    with pytest.raises(CboeDataError, match="CLOSE"):
        parse_cboe_history_csv("DATE,SETTLE\n01/03/2006,23.5\n", COR1M)


def test_parse_cboe_rejects_an_all_unusable_payload():
    with pytest.raises(CboeDataError, match="zero usable rows"):
        parse_cboe_history_csv("DATE,CLOSE\n01/03/2006,-1.0\n", COR1M)


def test_fetch_uses_an_injected_client_and_never_touches_the_network():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text=_CSV)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    frame = fetch_cboe_implied_correlation(client=client)
    assert list(frame.columns) == list(IMPLIED_CORRELATION_INDICES)
    assert len(calls) == len(IMPLIED_CORRELATION_INDICES)
    assert all(url.endswith("_History.csv") for url in calls)


def test_fetch_raises_on_an_http_error():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(httpx.HTTPStatusError):
        fetch_cboe_implied_correlation(client=client)


def test_verified_starts_record_the_live_2026_pull():
    assert CBOE_VERIFIED_START[COR1M] == date(2006, 1, 3)
    assert CBOE_VERIFIED_START[COR3M] == date(2006, 1, 3)


# --- realized correlation (pure math, seed-verified) ----------------------


def test_rolling_correlation_matches_a_hand_computed_window():
    """Against the mean off-diagonal of pandas' own correlation matrix on the
    same window — the definition this function reuses, not reimplements."""
    index = _calendar(60)
    rng = np.random.default_rng(21)
    returns = pd.DataFrame(rng.normal(0, 0.01, (60, 4)), index=index, columns=list("ABCD"))
    rolled = rolling_average_pairwise_correlation(returns, 21, as_percent=False)
    window = returns.iloc[9:30]
    matrix = window.corr().to_numpy()
    expected = (matrix.sum() - np.trace(matrix)) / (4 * 3)
    assert rolled.loc[index[29]] == pytest.approx(expected)


def test_rolling_correlation_recovers_a_known_equicorrelation():
    """A one-factor construction with equal loadings has a known population
    average pairwise correlation; the estimate must land near it."""
    n = 4000
    rng = np.random.default_rng(99)
    factor = rng.normal(0, 1, n)
    # x_i = f + e_i with var(f)=var(e)=1 -> pairwise corr = 1/(1+1) = 0.5
    frame = pd.DataFrame(
        {f"a{i}": factor + rng.normal(0, 1, n) for i in range(6)},
        index=pd.bdate_range(_START, periods=n),
    )
    rolled = rolling_average_pairwise_correlation(frame, 252, as_percent=False)
    assert rolled.mean() == pytest.approx(0.5, abs=0.03)


def test_rolling_correlation_has_no_look_ahead():
    """The value at date t must be unchanged by anything after t."""
    index = _calendar(400)
    rng = np.random.default_rng(4)
    returns = pd.DataFrame(rng.normal(0, 0.01, (400, 5)), index=index, columns=list("ABCDE"))
    full = rolling_average_pairwise_correlation(returns, 21)
    truncated = rolling_average_pairwise_correlation(returns.iloc[:200], 21)
    pd.testing.assert_series_equal(full.loc[truncated.index], truncated)


def test_rolling_correlation_window_ends_at_the_labelled_date():
    index = _calendar(30)
    rng = np.random.default_rng(6)
    returns = pd.DataFrame(rng.normal(0, 0.01, (30, 3)), index=index, columns=list("ABC"))
    rolled = rolling_average_pairwise_correlation(returns, 10)
    # The first value a 10-row window can produce is at row 10 (index 9).
    assert rolled.index[0] == index[9]
    assert len(rolled) == 21


def test_rolling_correlation_is_percent_scaled_to_match_cboe():
    """CRP subtracts realized from a CBOE print where 35.54 means 35.54%; the
    two must be in the same units or the subtraction is meaningless."""
    index = _calendar(300)
    rng = np.random.default_rng(8)
    returns = pd.DataFrame(rng.normal(0, 0.01, (300, 4)), index=index, columns=list("ABCD"))
    as_pct = rolling_average_pairwise_correlation(returns, 21, as_percent=True)
    as_unit = rolling_average_pairwise_correlation(returns, 21, as_percent=False)
    pd.testing.assert_series_equal(as_pct, as_unit * 100.0)


def test_rolling_correlation_rejects_a_degenerate_window():
    index = _calendar(30)
    returns = pd.DataFrame(np.zeros((30, 3)), index=index, columns=list("ABC"))
    with pytest.raises(ValueError, match="window must be >= 2"):
        rolling_average_pairwise_correlation(returns, 1)


def test_rolling_correlation_declines_below_the_name_floor():
    index = _calendar(60)
    rng = np.random.default_rng(12)
    returns = pd.DataFrame(rng.normal(0, 0.01, (60, 2)), index=index, columns=list("AB"))
    assert MIN_NAMES_FOR_REALIZED_CORRELATION == 3
    assert rolling_average_pairwise_correlation(returns, 21).empty


def test_correlation_risk_premium_is_implied_minus_realized_on_shared_dates():
    index = _calendar(10)
    implied = pd.Series(np.arange(10, dtype=float) + 30.0, index=index)
    realized = pd.Series(np.full(10, 25.0), index=index)
    realized.iloc[3] = np.nan
    premium = correlation_risk_premium(implied, realized)
    assert len(premium) == 9
    assert index[3] not in premium.index
    assert premium.loc[index[0]] == pytest.approx(5.0)
    assert premium.loc[index[9]] == pytest.approx(14.0)


# --- alignment -------------------------------------------------------------


def test_align_uses_the_traded_calendar():
    index = _calendar(400)
    spy = _spy(index).drop(index[100])
    data = _data(index, spy=spy)
    assert index[100] not in data.traded_close.index
    assert data.implied.index.equals(data.traded_close.index)
    assert data.realized.index.equals(data.traded_close.index)
    assert data.vix.index.equals(data.traded_close.index)


def test_align_forward_fills_a_missing_cboe_print_within_the_limit():
    """Carrying an OLDER print forward uses only past information — it can
    stale the signal but can never leak look-ahead."""
    index = _calendar(400)
    implied = _implied_frame(index)
    implied.iloc[200] = np.nan
    data = _data(index, implied=implied)
    assert data.implied[COR1M].iloc[200] == pytest.approx(implied[COR1M].iloc[199])


def test_align_stops_forward_filling_past_the_limit():
    index = _calendar(400)
    implied = _implied_frame(index)
    gap = slice(200, 200 + CBOE_FFILL_LIMIT_DAYS + 3)
    implied.iloc[gap] = np.nan
    data = _data(index, implied=implied)
    filled = data.implied[COR1M].iloc[gap]
    assert filled.iloc[: CBOE_FFILL_LIMIT_DAYS].notna().all()
    assert filled.iloc[CBOE_FFILL_LIMIT_DAYS :].isna().all()


def test_align_computes_both_realized_windows():
    data = _data()
    assert f"realized_{REALIZED_WINDOW_1M}" in data.realized.columns
    assert f"realized_{REALIZED_WINDOW_3M}" in data.realized.columns


def test_crp_data_rejects_misaligned_frames():
    index = _calendar(400)
    data = _data(index)
    with pytest.raises(ValueError, match="align_crp_data"):
        CrpData(
            implied=data.implied.iloc[:-5],
            realized=data.realized,
            vix=data.vix,
            traded_close=data.traded_close,
        )
    with pytest.raises(ValueError, match="align_crp_data"):
        CrpData(
            implied=data.implied,
            realized=data.realized,
            vix=data.vix.iloc[:-5],
            traded_close=data.traded_close,
        )


# --- backtest mechanics ----------------------------------------------------


def _constant_state(value: float):
    return lambda data, _w: pd.Series(value, index=data.traded_close.index, dtype=float)


@pytest.mark.parametrize("holding", CRP_HOLDING_DAYS)
def test_formations_are_non_overlapping_and_adjacent(holding):
    data = _data()
    replay = run_crp_backtest(data, _spec(_constant_state(0.5), holding), _config())
    positions = [data.traded_close.index.get_loc(pd.Timestamp(f.formation_date)) for f in replay.formations]
    gaps = np.diff(positions)
    assert set(gaps) == {holding}


@pytest.mark.parametrize("holding", CRP_HOLDING_DAYS)
def test_no_realized_day_is_counted_twice(holding):
    data = _data()
    replay = run_crp_backtest(data, _spec(_constant_state(0.5), holding), _config())
    assert replay.daily_returns.index.is_unique
    assert replay.daily_returns.index.is_monotonic_increasing


def test_returns_start_the_day_after_formation_never_on_it():
    data = _data()
    replay = run_crp_backtest(data, _spec(_constant_state(0.5), 21), _config())
    first_formation = pd.Timestamp(replay.formations[0].formation_date)
    assert replay.daily_returns.index[0] > first_formation


def test_position_is_constant_within_a_hold():
    data = _data()
    replay = run_crp_backtest(data, _spec(_constant_state(0.4), 21), _config())
    first = replay.positions.iloc[:21]
    assert first.nunique() == 1


def test_future_data_cannot_change_past_positions():
    """The look-ahead test that matters: truncating the sample must leave every
    surviving position identical."""
    index = _calendar()
    full = _data(index)
    spec = _spec(lambda d, w: state_crp(d, w, implied_key=COR1M, realized_window=REALIZED_WINDOW_1M), 21)
    long_replay = run_crp_backtest(full, spec, _config())

    cut = index[:1200]
    short = _data(cut)
    short_replay = run_crp_backtest(short, spec, _config())

    shared = short_replay.positions.index.intersection(long_replay.positions.index)
    assert len(shared) > 200
    pd.testing.assert_series_equal(
        long_replay.positions.loc[shared], short_replay.positions.loc[shared]
    )


def test_position_is_clipped_to_unit_leverage():
    data = _data()
    replay = run_crp_backtest(data, _spec(_constant_state(9.0), 21), _config())
    assert replay.positions.max() == pytest.approx(1.0)
    replay_short = run_crp_backtest(data, _spec(_constant_state(-9.0), 21), _config())
    assert replay_short.positions.min() == pytest.approx(-1.0)


def test_position_sign_follows_the_pre_declared_direction():
    """CRP_DIRECTION is +1: a high (positive-z) premium goes LONG equities."""
    data = _data()
    replay = run_crp_backtest(data, _spec(_constant_state(0.6), 21), _config())
    assert (replay.positions > 0).all()


def test_uncomputable_state_skips_the_hold_instead_of_recording_zeros():
    """Forced zeros would shrink both the mean and the std of the return
    series and report the Sharpe of 'hold cash, then trade' as the signal's."""
    data = _data()
    nan_state = lambda d, _w: pd.Series(np.nan, index=d.traded_close.index, dtype=float)
    replay = run_crp_backtest(data, _spec(nan_state, 21), _config())
    assert replay.status == "no_realized_returns"
    assert replay.daily_returns.empty
    assert replay.n_skipped_formations > 0


def test_leading_warmup_skips_are_not_counted_as_interior_skips():
    data = _data()
    spec = _spec(lambda d, w: state_crp(d, w, implied_key=COR1M, realized_window=REALIZED_WINDOW_3M), 21)
    replay = run_crp_backtest(data, spec, _config(formation_start=date(2010, 1, 5)))
    assert replay.n_skipped_formations > 0
    assert replay.n_interior_skips == 0


def test_a_feed_dying_mid_sample_is_counted_as_an_interior_skip(caplog):
    data = _data()
    index = data.traded_close.index

    def dying(d, _w):
        series = pd.Series(0.5, index=index, dtype=float)
        series.iloc[900:] = np.nan
        return series

    replay = run_crp_backtest(data, _spec(dying, 21), _config())
    assert replay.n_interior_skips > 0


def test_start_after_all_history_yields_a_named_status():
    data = _data()
    replay = run_crp_backtest(data, _spec(_constant_state(0.5), 21), _config(formation_start=date(2099, 1, 1)))
    assert replay.status == "no_history_after_start"


# --- costs and financing ---------------------------------------------------


def test_turnover_cost_is_one_leg_not_two():
    """SPY outright trades ONE unit of gross notional per unit of position,
    unlike vol_regime_timing's two-legged spread which trades 2.0."""
    data = _data()
    config = _config(cost_bps=10.0)
    replay = run_crp_backtest(data, _spec(_constant_state(1.0), 21), config)
    opening = replay.formations[0]
    assert opening.turnover == pytest.approx(1.0)
    assert opening.cost == pytest.approx(10.0 / 1e4 * 1.0)


def test_total_cost_is_the_sum_of_formation_costs():
    data = _data()
    replay = run_crp_backtest(data, _spec(_constant_state(0.5), 21), _config(cost_bps=5.0))
    assert replay.total_cost == pytest.approx(sum(f.cost for f in replay.formations))


def test_zero_cost_config_leaves_returns_gross():
    data = _data()
    free = _config(cost_bps=0.0, financing_bps_per_year=0.0)
    replay = run_crp_backtest(data, _spec(_constant_state(1.0), 21), free)
    assert replay.total_cost == pytest.approx(0.0)
    assert replay.total_financing_cost == pytest.approx(0.0)


def test_higher_cost_monotonically_reduces_net_return():
    data = _data()
    spec = _spec(_constant_state(0.5), 21)
    cheap = run_crp_backtest(data, spec, _config(cost_bps=1.0)).daily_returns.sum()
    dear = run_crp_backtest(data, spec, _config(cost_bps=25.0)).daily_returns.sum()
    assert dear < cheap


def test_financing_is_charged_on_both_signs():
    """THE difference from vol_regime_timing: that family traded a genuinely
    self-financing dollar-neutral spread and charged borrow on the short leg
    only. An outright SPY position must be FUNDED when long and pays borrow
    when short, so a symmetric position must pay symmetric financing."""
    data = _data()
    config = _config(cost_bps=0.0)
    long_only = run_crp_backtest(data, _spec(_constant_state(0.75), 21), config)
    short_only = run_crp_backtest(data, _spec(_constant_state(-0.75), 21), config)
    assert long_only.total_financing_cost > 0
    assert long_only.total_financing_cost == pytest.approx(short_only.total_financing_cost)


def test_financing_scales_with_absolute_position():
    data = _data()
    config = _config(cost_bps=0.0)
    half = run_crp_backtest(data, _spec(_constant_state(0.5), 21), config).total_financing_cost
    full = run_crp_backtest(data, _spec(_constant_state(1.0), 21), config).total_financing_cost
    assert full == pytest.approx(2.0 * half)


def test_financing_accrues_on_calendar_days_so_a_weekend_costs_three():
    """Charging per TRADING day would undercharge a continuously-held book by
    ~31%. Same reasoning as cross_sectional.FINANCING_DAYS_PER_YEAR."""
    data = _data()
    config = _config(cost_bps=0.0)
    replay = run_crp_backtest(data, _spec(_constant_state(1.0), 21), config)
    index = replay.daily_returns.index
    elapsed = pd.Series(index).diff().dt.days.dropna()
    # A business-day calendar has Monday gaps of 3 calendar days.
    assert (elapsed == 3).any()
    total_days = (index[-1] - index[0]).days
    rate = config.financing_bps_per_year / 1e4 / 365.0
    assert replay.total_financing_cost == pytest.approx(rate * total_days, rel=0.02)


def test_financing_and_turnover_are_reported_separately():
    """They push in opposite directions across the holding_days axis this
    family searches over, so summing them would hide the trade-off."""
    data = _data()
    replay = run_crp_backtest(data, _spec(_constant_state(0.5), 21), _config(cost_bps=5.0))
    assert replay.total_cost > 0
    assert replay.total_financing_cost > 0
    assert replay.total_cost != replay.total_financing_cost


def test_shorter_holds_pay_more_turnover_cost():
    data = _data()
    index = data.traded_close.index
    rng = np.random.default_rng(31)
    noisy = pd.Series(rng.normal(0, 1, len(index)), index=index)
    state = lambda d, _w: noisy
    short_hold = run_crp_backtest(data, _spec(state, 5), _config()).total_cost
    long_hold = run_crp_backtest(data, _spec(state, 63), _config()).total_cost
    assert short_hold > long_hold


# --- signal quality --------------------------------------------------------


def test_a_perfectly_predictive_state_produces_a_strongly_positive_sharpe():
    """Sanity floor: if the harness cannot make money from a state that
    literally knows the next hold's direction, no negative result it produces
    means anything."""
    index = _calendar(1300)
    holding = 21
    rng = np.random.default_rng(77)
    steps = rng.normal(0.0006, 0.011, len(index))
    # Alternate the sign of each hold's drift, and hand the state that sign.
    signs = np.repeat(np.where(np.arange(len(index) // holding + 2) % 2 == 0, 1.0, -1.0), holding)[
        : len(index)
    ]
    spy = pd.Series(400.0 * np.cumprod(1 + np.abs(steps) * signs), index=index, name=TRADED_TICKER)
    data = _data(index, spy=spy)
    aligned_signs = pd.Series(signs, index=index).reindex(data.traded_close.index)
    replay = run_crp_backtest(
        data,
        _spec(lambda d, _w: aligned_signs.shift(-1).ffill(), holding),
        _config(formation_start=date(2010, 1, 5)),
    )
    assert sharpe_ratio(replay.daily_returns) > 2.0


def test_a_pure_noise_state_produces_a_near_zero_sharpe():
    index = _calendar()
    data = _data(index)
    rng = np.random.default_rng(404)
    noise = pd.Series(rng.normal(0, 1, len(data.traded_close)), index=data.traded_close.index)
    replay = run_crp_backtest(data, _spec(lambda d, _w: noise, 21), _config())
    assert abs(sharpe_ratio(replay.daily_returns)) < 1.0


# --- confound diagnostics --------------------------------------------------


def test_a_pure_static_tilt_is_exposed_by_a_near_zero_residual_sharpe():
    """The regression that reduced this project's commodities family to
    residual Sharpe ~0.000. A constant long-SPY position has NO timing content
    and must be reported as having none, however good its raw Sharpe looks."""
    index = _calendar()
    rng = np.random.default_rng(55)
    spy = pd.Series(
        400.0 * np.cumprod(1 + rng.normal(0.0008, 0.010, len(index))), index=index, name=TRADED_TICKER
    )
    data = _data(index, spy=spy)
    spec = _spec(_constant_state(1.0), 21)
    replay = run_crp_backtest(data, spec, _config(cost_bps=0.0, financing_bps_per_year=0.0))
    diagnostic = compute_confound_diagnostics(spec, replay)
    assert diagnostic.spy_beta == pytest.approx(1.0, abs=0.02)
    assert abs(diagnostic.residual_sharpe) < 0.1
    assert sharpe_ratio(replay.daily_returns) > 0.5
    assert diagnostic.mean_position == pytest.approx(1.0)
    assert diagnostic.fraction_long == pytest.approx(1.0)


def test_a_numerically_perfect_hedge_reports_zero_not_floating_point_dust():
    """REGRESSION TEST for a bug this suite actually caught.

    A Sharpe ratio is SCALE-INVARIANT, so a hedged stream that is
    mathematically zero but numerically ~1e-18 still reports whatever Sharpe
    its floating-point dust happens to have. For a spec pinned at position 1.0
    the strategy returns are BIT-IDENTICAL to the benchmark (verified below:
    max|y - x| == 0.0), yet compute_beta returns 1.0000000000000002, leaving
    hedged = -2e-16 * x — a scaled copy of the BENCHMARK, whose Sharpe was
    reported as -0.836. The most blatant possible static tilt was thus being
    described with a confident-looking negative alpha instead of 'nothing is
    left'. RESIDUAL_DEGENERACY_RATIO guards it."""
    index = _calendar()
    rng = np.random.default_rng(55)
    spy = pd.Series(
        400.0 * np.cumprod(1 + rng.normal(0.0008, 0.010, len(index))),
        index=index,
        name=TRADED_TICKER,
    )
    data = _data(index, spy=spy)
    spec = _spec(_constant_state(1.0), 21)
    replay = run_crp_backtest(data, spec, _config(cost_bps=0.0, financing_bps_per_year=0.0))

    aligned = pd.concat(
        [replay.daily_returns.rename("y"), replay.benchmark_returns.rename("x")], axis=1
    ).dropna()
    assert float((aligned["y"] - aligned["x"]).abs().max()) == 0.0

    diagnostic = compute_confound_diagnostics(spec, replay)
    assert diagnostic.residual_sharpe == 0.0
    assert diagnostic.spy_alpha_annualized == 0.0


def test_a_genuine_small_residual_is_not_swallowed_by_the_degeneracy_guard():
    """The guard must not silence real alpha. A residual many orders of
    magnitude above double-precision dust has to survive."""
    index = _calendar()
    rng = np.random.default_rng(56)
    spy = pd.Series(
        400.0 * np.cumprod(1 + rng.normal(0.0005, 0.010, len(index))),
        index=index,
        name=TRADED_TICKER,
    )
    data = _data(index, spy=spy)
    spec = _spec(_constant_state(1.0), 21)
    replay = run_crp_backtest(data, spec, _config(cost_bps=0.0, financing_bps_per_year=0.0))
    # A genuine independent return stream on top of the pure market exposure.
    extra = pd.Series(rng.normal(0.0004, 0.002, len(replay.daily_returns)), index=replay.daily_returns.index)
    replay.daily_returns = replay.daily_returns + extra
    diagnostic = compute_confound_diagnostics(spec, replay)
    assert diagnostic.residual_sharpe > 1.0
    assert diagnostic.spy_alpha_annualized > 0.0


def test_a_genuine_timing_signal_keeps_its_residual_sharpe():
    """REGRESSION GUARD against computing the OLS residual (y - alpha - beta*x)
    instead of the beta-hedged stream (y - beta*x): an OLS residual with an
    intercept has mean exactly zero by construction, so its Sharpe is ~0 for
    EVERY strategy and this diagnostic would condemn all of them."""
    index = _calendar(1300)
    holding = 21
    rng = np.random.default_rng(78)
    steps = np.abs(rng.normal(0.0006, 0.011, len(index)))
    signs = np.repeat(np.where(np.arange(len(index) // holding + 2) % 2 == 0, 1.0, -1.0), holding)[
        : len(index)
    ]
    spy = pd.Series(400.0 * np.cumprod(1 + steps * signs), index=index, name=TRADED_TICKER)
    data = _data(index, spy=spy)
    aligned = pd.Series(signs, index=index).reindex(data.traded_close.index)
    spec = _spec(lambda d, _w: aligned.shift(-1).ffill(), holding)
    replay = run_crp_backtest(data, spec, _config(formation_start=date(2010, 1, 5)))
    diagnostic = compute_confound_diagnostics(spec, replay)
    assert diagnostic.residual_sharpe > 1.5


def test_subperiod_sharpes_split_the_sample_into_thirds():
    data = _data()
    spec = _spec(_constant_state(0.5), 21)
    replay = run_crp_backtest(data, spec, _config())
    diagnostic = compute_confound_diagnostics(spec, replay)
    assert len(diagnostic.subperiod_sharpes) == 3


def test_subperiod_sharpes_expose_one_crisis_dependence():
    """A signal that earns everything in one window must not look uniform."""
    index = _calendar(900)
    data = _data(index)
    spec = _spec(_constant_state(1.0), 21)
    replay = run_crp_backtest(data, spec, _config(cost_bps=0.0, financing_bps_per_year=0.0))
    crisis = replay.daily_returns.copy()
    crisis.iloc[: len(crisis) // 3] += 0.01
    replay.daily_returns = crisis
    diagnostic = compute_confound_diagnostics(spec, replay)
    assert diagnostic.subperiod_sharpes[0] > diagnostic.subperiod_sharpes[2]


def test_confound_diagnostics_are_computed_for_every_screened_spec():
    data = _data()
    results = screen_crp_timing(data, CRP_FAMILY, _config())
    assert results
    for result in results:
        assert result.confound.spec_id == result.spec_id
        assert np.isfinite(result.confound.spy_beta)
        assert result.confound.n_formations > 0


# --- THE overlap check -----------------------------------------------------


def test_the_vix_control_overlaps_perfectly_with_itself_and_is_flagged():
    """A vix_level spec IS the rejected family's signal, so it must print 1.000
    and be marked suspect. If this ever stops holding, the check is broken."""
    data = _data()
    results = screen_crp_timing(data, CRP_FAMILY, _config())
    vix_results = [r for r in results if r.state_key == VIX_CONTROL_KEY]
    assert len(vix_results) == len(CRP_HOLDING_DAYS)
    for result in vix_results:
        assert result.overlap.signal_level_corr_vs_vix == pytest.approx(1.0)
        assert result.overlap.return_corr_vs_vix_spec == pytest.approx(1.0)
        assert result.overlap.is_suspect


def test_an_orthogonal_signal_is_not_flagged_suspect():
    data = _data()
    index = data.traded_close.index
    rng = np.random.default_rng(202)
    noise = pd.Series(rng.normal(0, 1, len(index)), index=index)
    spec = _spec(lambda d, _w: noise, 21, state_key="noise")
    replay = run_crp_backtest(data, spec, _config())
    vix_state = state_vix_level(data, CRP_Z_WINDOW)
    overlap = compute_overlap_diagnostics(spec, replay, vix_state, None)
    assert abs(overlap.signal_level_corr_vs_vix) < CRP_VIX_OVERLAP_THRESHOLD
    assert not overlap.is_suspect
    assert "No overlap breach" in overlap.reason


def test_a_signal_that_is_vix_relabelled_is_flagged_on_levels_alone():
    """Even with no return series to compare, a signal whose LEVELS track the
    rejected family's must be caught — the level is what sets the position."""
    data = _data()
    vix_state = state_vix_level(data, CRP_Z_WINDOW)
    spec = _spec(lambda d, w: state_vix_level(d, w) * 1.3 + 0.2, 21, state_key="disguised")
    replay = run_crp_backtest(data, spec, _config())
    overlap = compute_overlap_diagnostics(spec, replay, vix_state, None)
    assert overlap.signal_level_corr_vs_vix == pytest.approx(1.0)
    assert overlap.is_suspect
    assert "OVERLAP SUSPECT" in overlap.reason


def test_overlap_is_reported_for_every_spec_never_on_request_only():
    data = _data()
    results = screen_crp_timing(data, CRP_FAMILY, _config())
    for result in results:
        assert result.overlap.spec_id == result.spec_id
        assert result.overlap.threshold == CRP_VIX_OVERLAP_THRESHOLD
        assert result.overlap.reason


def test_overlap_threshold_is_the_pre_declared_half():
    assert CRP_VIX_OVERLAP_THRESHOLD == 0.5


def test_overlap_declines_rather_than_guessing_on_a_short_overlap():
    data = _data()
    index = data.traded_close.index
    spec = _spec(_constant_state(0.5), 21)
    replay = run_crp_backtest(data, spec, _config())
    tiny = pd.Series(np.arange(10.0), index=index[:10])
    overlap = compute_overlap_diagnostics(spec, replay, tiny, None)
    assert overlap.signal_level_corr_vs_vix is None
    assert not overlap.is_suspect


# --- point-in-time cross-check --------------------------------------------


def test_pit_crosscheck_reports_tracking_between_two_correlated_measures():
    index = pd.bdate_range("2016-01-04", periods=700)
    rng = np.random.default_rng(64)
    factor = rng.normal(0, 0.01, len(index))
    sector_returns = pd.DataFrame(
        {t: factor + rng.normal(0, 0.01, len(index)) for t in SECTOR_ETF_UNIVERSE}, index=index
    )
    members = crp_mod.get_universe_as_of(date(2017, 1, 3))[:40]
    constituents = pd.DataFrame(
        {m: 100.0 * np.cumprod(1 + factor + rng.normal(0, 0.02, len(index))) for m in members},
        index=index,
    )
    result = compute_pit_realized_correlation_crosscheck(sector_returns, constituents)
    assert result.status == "ok"
    assert result.n_dates > 10
    assert result.level_correlation is not None
    assert -1.0 <= result.level_correlation <= 1.0
    assert result.mean_names is not None and result.mean_names > 5
    assert any("delisted" in note for note in result.notes)


def test_pit_crosscheck_declines_before_membership_coverage_begins():
    index = pd.bdate_range("2010-01-04", periods=300)
    rng = np.random.default_rng(65)
    sector_returns = pd.DataFrame(
        {t: rng.normal(0, 0.01, len(index)) for t in SECTOR_ETF_UNIVERSE}, index=index
    )
    constituents = pd.DataFrame({"AAPL": np.full(len(index), 100.0)}, index=index)
    result = compute_pit_realized_correlation_crosscheck(sector_returns, constituents)
    assert result.status in {"insufficient_history", "insufficient_constituents"}


def test_pit_crosscheck_handles_no_data():
    empty = pd.DataFrame()
    assert compute_pit_realized_correlation_crosscheck(empty, empty).status == "no_data"


# --- screening -------------------------------------------------------------


def test_n_trials_is_the_declared_family_size_not_the_survivor_count():
    """Shrinking the denominator to 'specs that worked' would be gameable by
    declaring specs expected to fail."""
    index = _calendar(700)
    data = _data(index)
    results = screen_crp_timing(data, CRP_FAMILY, _config())
    assert len(results) <= len(CRP_FAMILY)
    for result in results:
        assert result.deflated_sharpe.n_trials == len(CRP_FAMILY) == CRP_N_TRIALS


def test_sigma_sr_is_the_sibling_sharpe_dispersion():
    data = _data()
    results = screen_crp_timing(data, CRP_FAMILY, _config())
    assert len(results) >= 2
    expected = float(np.std([r.sharpe_annualized for r in results], ddof=1))
    for result in results:
        assert result.deflated_sharpe.sigma_sr_annualized == pytest.approx(expected)


def test_results_are_sorted_by_sharpe_descending():
    data = _data()
    results = screen_crp_timing(data, CRP_FAMILY, _config())
    sharpes = [r.sharpe_annualized for r in results]
    assert sharpes == sorted(sharpes, reverse=True)


def test_specs_below_the_replay_floor_are_dropped():
    data = _data(_calendar(400))
    results = screen_crp_timing(data, CRP_FAMILY, _config())
    for result in results:
        assert result.n_trading_days >= MIN_REPLAY_TRADING_DAYS


def test_net_cumulative_return_plus_charges_reconstructs_the_pre_cost_return():
    """The additivity the breakeven-cost arithmetic depends on."""
    data = _data()
    spec = CRP_FAMILY[0]
    config = _config()
    costed = screen_crp_timing(data, [spec], config)[0]
    free = run_crp_backtest(data, spec, _config(cost_bps=0.0, financing_bps_per_year=0.0))
    reconstructed = (
        costed.net_cumulative_return + costed.total_cost_drag + costed.total_financing_drag
    )
    assert reconstructed == pytest.approx(float(free.daily_returns.sum()), abs=1e-9)


def test_screening_reports_every_declared_field():
    data = _data()
    results = screen_crp_timing(data, CRP_FAMILY, _config())
    assert results
    for result in results:
        assert result.state_key
        assert result.holding_days in CRP_HOLDING_DAYS
        assert result.n_formations > 0
        assert result.first_formation is not None
        assert result.first_formation <= result.last_formation
        assert np.isfinite(result.net_cumulative_return)
        assert result.total_cost_drag >= 0
        assert result.total_financing_drag >= 0


def test_empty_spec_list_returns_no_results():
    assert screen_crp_timing(_data(), [], _config()) == []


# --- disclosure ------------------------------------------------------------


def test_disclosure_states_the_uncounted_prior_search():
    """The correction that sank this project's buyback family — it must be
    impossible to read these results without it."""
    data = _data()
    results = screen_crp_timing(data, CRP_FAMILY, _config())
    joined = " ".join(build_crp_disclosure(results, _config()))
    assert "UPPER BOUND" in joined
    assert "NOT in the denominator" in joined
    assert "15" in joined


def test_disclosure_states_the_sector_proxy_level_bias():
    """The single largest known weakness of the construction must travel with
    every number it produces."""
    data = _data()
    results = screen_crp_timing(data, CRP_FAMILY, _config())
    joined = " ".join(build_crp_disclosure(results, _config()))
    assert "not the Driessen-Maenhout-Vilkov premium" in joined
    assert "sector ETFs" in joined


def test_disclosure_states_costs_direction_and_overlap_discipline():
    data = _data()
    results = screen_crp_timing(data, CRP_FAMILY, _config())
    joined = " ".join(build_crp_disclosure(results, _config()))
    assert "non-overlapping" in joined
    assert "block bootstrap" in joined
    assert "never fitted per spec" in joined
    assert "not self-financing" in joined
    assert "FLATTERS" in joined


def test_disclosure_always_reports_the_overlap_verdict():
    data = _data()
    results = screen_crp_timing(data, CRP_FAMILY, _config())
    joined = " ".join(build_crp_disclosure(results, _config()))
    # The vix_level controls always breach against themselves, so a real run
    # always carries the warning; the point is that a verdict is always stated.
    assert "vol_regime_timing" in joined
    assert "OVERLAP WARNING" in joined or "Overlap check" in joined


def test_static_tilt_detector_uses_a_signed_not_absolute_comparison():
    """REGRESSION TEST. With a near-constant position the hedge is near-perfect,
    only the cost drag remains, and its Sharpe is a large NEGATIVE number. An
    abs()-based threshold would clear the most blatant possible static tilt."""

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
            self.overlap = type(
                "O", (), {"is_suspect": False, "signal_change_corr_vs_vix": 0.1}
            )()
            self.is_crp_hypothesis = True
            self.deflated_sharpe = type("D", (), {"dsr": 0.3})()

    blatant = _Stub(sharpe=1.2, residual=-20.0)
    genuine = _Stub(sharpe=1.2, residual=1.1)
    assert "long-market tilts" in " ".join(build_crp_disclosure([blatant], _config()))
    assert "long-market tilts" not in " ".join(build_crp_disclosure([genuine], _config()))


def test_disclosure_survives_an_empty_result_set():
    lines = build_crp_disclosure([], _config())
    assert any("nothing to interpret" in line for line in lines)


# --- end-to-end with a stubbed provider ------------------------------------


class _StubProvider:
    def __init__(self, closes: pd.DataFrame):
        self._closes = closes

    def get_price_history(self, tickers, start, end):
        available = [t for t in tickers if t in self._closes.columns]
        missing = [t for t in tickers if t not in self._closes.columns]
        return self._closes[available], missing


def test_run_crp_screening_end_to_end_without_network():
    index = _calendar()
    closes = _sector_frame(index)
    closes[TRADED_TICKER] = _spy(index)
    closes[VIX] = _vix(index)
    implied = _implied_frame(index)

    csv_by_symbol = {
        symbol: "DATE,CLOSE\n"
        + "".join(
            f"{ts.strftime('%m/%d/%Y')},{value:.4f}\n"
            for ts, value in implied[symbol].items()
        )
        for symbol in IMPLIED_CORRELATION_INDICES
    }

    def handler(request: httpx.Request) -> httpx.Response:
        symbol = str(request.url).rsplit("/", 1)[-1].replace("_History.csv", "")
        return httpx.Response(200, text=csv_by_symbol[symbol])

    summary = run_crp_screening(
        start=date(2011, 1, 3),
        end=date(2016, 1, 1),
        provider=_StubProvider(closes),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        include_pit_crosscheck=False,
    )
    assert summary.results
    assert summary.cboe_starts[COR1M] == index[0].date()
    assert summary.cboe_rows[COR1M] == len(index)
    assert summary.formation_calendar_start is not None
    assert summary.disclosure
    for result in summary.results:
        assert result.deflated_sharpe.n_trials == CRP_N_TRIALS
        assert result.overlap.reason
    disclosure_text = " ".join(summary.disclosure)
    assert "Best DSR:" in disclosure_text
    assert "Signal-CHANGE correlation" in disclosure_text


def test_run_crp_screening_reports_missing_instruments_rather_than_crashing():
    index = _calendar(600)
    closes = _sector_frame(index)  # no SPY at all
    handler = lambda r: httpx.Response(200, text=_CSV)
    summary = run_crp_screening(
        start=date(2011, 1, 3),
        end=date(2013, 1, 1),
        provider=_StubProvider(closes),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        include_pit_crosscheck=False,
    )
    assert summary.results == []
    assert TRADED_TICKER in summary.missing_instruments


# --- live-data integration check (opt-in) ---------------------------------

_LIVE = os.getenv("ALADDIN_LIVE_DATA_TESTS") == "1"


@pytest.mark.skipif(not _LIVE, reason="set ALADDIN_LIVE_DATA_TESTS=1 to hit the live CBOE endpoint")
def test_live_cboe_endpoint_still_serves_real_history():
    """The one network test. Verifies the free, unauthenticated CBOE feed this
    whole family rests on is still live and still deep — the assumption most
    likely to rot silently, and the exact category this project's standing
    rule says to re-verify rather than assume."""
    frame = fetch_cboe_implied_correlation()
    for symbol in IMPLIED_CORRELATION_INDICES:
        series = frame[symbol].dropna()
        assert len(series) > 4000, f"{symbol} returned only {len(series)} rows"
        assert series.index[0].date() <= CBOE_VERIFIED_START[symbol] + pd.Timedelta(days=7)
        assert series.index[-1].date() >= date(2026, 1, 1)
        # Implied correlation is a percentage in a plausible band.
        assert 0.0 < series.min() < series.max() <= 100.0
