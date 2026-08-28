"""Tests for the EDGE spread-based cost model wiring (2026-08-28):

 * spread_estimator.build_edge_half_spread_frame — the frame builder the
   harness consumes: recovery of a KNOWN injected synthetic spread at the
   production COST_MODEL_WINDOW_DAYS window, trailing-ness (truncation
   invariance — the property that makes reading the formation row
   look-ahead-free), alignment validation, and the no-non-positive-cells
   contract.
 * cross_sectional cost_model="edge_spread" — per-ticker charging
   arithmetic against hand-built half-spread frames with exactly known
   expected costs, the NaN->flat-fallback path and its counted notional,
   the loud missing-frame / unknown-model rejections, and the additive
   guarantee that the default "flat_bps" ignores a supplied frame
   entirely.
 * intraday_patterns per-ticker cost threading — default unchanged,
   direction of a cost override, and the loud missing-ticker rejection in
   screen_pattern_universe's cost_bps_by_ticker.

The synthetic-spread generator here reproduces the validation setup
documented in spread_estimator.py's own header (efficient mid-price random
walk; each observed trade bounces to bid or ask, half the true spread away;
daily OHLC taken over the day's observed trades)."""

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    run_cross_sectional_backtest,
    screen_cross_sectional_universe,
    validate_cross_sectional_data,
)
from app.services.research_lab.intraday_patterns import (
    INTRADAY_COST_BPS,
    PatternSignal,
    PatternSpec,
    backtest_patterns_for_ticker,
    build_pattern_raw_data,
    run_pattern_backtest,
    screen_pattern_universe,
)
from app.services.research_lab.spread_estimator import (
    COST_MODEL_WINDOW_DAYS,
    build_edge_half_spread_frame,
)
from tests.test_intraday_patterns import _synthetic_ticker_bars


def ALWAYS_MEMBER(_ticker, _on) -> bool:
    return True


# --- fixtures ----------------------------------------------------------


def _close_frame(returns_by_ticker: dict[str, float], start: str, n_days: int) -> pd.DataFrame:
    """Constant-daily-return compounding paths — same fixture shape as
    test_cross_sectional.py's, so leg means and turnover are hand-checkable."""
    index = pd.bdate_range(start, periods=n_days)
    data = {
        ticker: 100.0 * np.cumprod(np.full(n_days, 1.0 + r))
        for ticker, r in returns_by_ticker.items()
    }
    return pd.DataFrame(data, index=index)


def _last_close_signal(view: CrossSectionalData) -> pd.Series:
    return view.close.iloc[-1]


def _spec(**overrides) -> CrossSectionalSpec:
    defaults = {
        "pattern_id": "edge_cost_test_spec",
        "family": "test",
        "citation": "test fixture, not a real citation",
        "signal_fn": _last_close_signal,
        "lookback_days": 10,
        "holding_days": 5,
        "portfolio": "long_short",
        "rank_fraction": 0.25,
    }
    defaults.update(overrides)
    return CrossSectionalSpec(**defaults)


# Four tickers with strictly ordered constant returns: rank_fraction=0.25
# makes every formation long exactly A (highest cumulative close) and short
# exactly D, weight 1.0 each — so the FIRST formation trades gross notional
# 2.0 and every later formation reforms the identical book (turnover 0.0),
# giving one exactly-predictable cost charge for the whole replay.
RETURNS = {"A": 0.01, "B": 0.001, "C": -0.001, "D": -0.01}


def _half_spread_frame(close: pd.DataFrame, by_ticker: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {t: np.full(len(close.index), by_ticker[t]) for t in close.columns},
        index=close.index,
    )[close.columns]


def _run(close: pd.DataFrame, config: CrossSectionalConfig, half_spread: pd.DataFrame | None = None):
    data = CrossSectionalData(close=close, half_spread=half_spread)
    return run_cross_sectional_backtest(data, _spec(), config, membership_fn=ALWAYS_MEMBER)


# --- harness: charging arithmetic --------------------------------------


def test_default_cost_model_is_flat_and_ignores_a_supplied_half_spread_frame():
    close = _close_frame(RETURNS, "2024-01-02", 30)
    hs = _half_spread_frame(close, {"A": 0.0050, "B": 0.0050, "C": 0.0050, "D": 0.0050})
    config = CrossSectionalConfig(cost_bps=5.0, min_names_per_leg=1)
    assert config.cost_model == "flat_bps"

    without_frame = _run(close, config, half_spread=None)
    with_frame = _run(close, config, half_spread=hs)
    with_explicit = _run(
        close, CrossSectionalConfig(cost_bps=5.0, min_names_per_leg=1, cost_model="flat_bps"), hs
    )

    pd.testing.assert_series_equal(without_frame.daily_returns, with_frame.daily_returns)
    pd.testing.assert_series_equal(without_frame.daily_returns, with_explicit.daily_returns)
    assert without_frame.total_cost == with_frame.total_cost
    assert all(f.edge_flat_fallback_notional == 0.0 for f in with_frame.formations)


def test_edge_spread_charges_each_ticker_its_own_half_spread():
    close = _close_frame(RETURNS, "2024-01-02", 30)
    # A (the long) 20bps, D (the short) 2bps — deliberately straddling the
    # 5bps flat rate so the direction of the change is informative both ways.
    hs = _half_spread_frame(close, {"A": 0.0020, "B": 0.0010, "C": 0.0010, "D": 0.0002})
    flat = _run(close, CrossSectionalConfig(cost_bps=5.0, min_names_per_leg=1))
    edge = _run(
        close,
        CrossSectionalConfig(cost_bps=5.0, min_names_per_leg=1, cost_model="edge_spread"),
        hs,
    )

    # Only the first formation trades (gross 2.0): flat charges
    # 2 * 5bps = 0.0010, edge charges 1.0*0.0020 + 1.0*0.0002 = 0.0022.
    assert flat.total_cost == pytest.approx(0.0010)
    assert edge.total_cost == pytest.approx(0.0022)

    diff = flat.daily_returns - edge.daily_returns
    assert diff.iloc[0] == pytest.approx(0.0022 - 0.0010)
    assert np.allclose(diff.iloc[1:], 0.0)

    # Both tickers had usable estimates — nothing fell back.
    assert all(f.edge_flat_fallback_notional == 0.0 for f in edge.formations)
    # The traded base itself is identical under both models.
    assert [f.turnover for f in flat.formations] == [f.turnover for f in edge.formations]


def test_edge_spread_nan_estimate_falls_back_to_flat_for_that_ticker_and_is_counted():
    close = _close_frame(RETURNS, "2024-01-02", 30)
    hs = _half_spread_frame(close, {"A": 0.0020, "B": 0.0010, "C": 0.0010, "D": 0.0002})
    hs["A"] = np.nan  # the long leg's ticker has no usable estimate
    edge = _run(
        close,
        CrossSectionalConfig(cost_bps=5.0, min_names_per_leg=1, cost_model="edge_spread"),
        hs,
    )
    # A charged at the flat 5bps, D at its own 2bps.
    assert edge.total_cost == pytest.approx(0.0005 + 0.0002)
    first = next(f for f in edge.formations if f.skipped_reason is None)
    assert first.edge_flat_fallback_notional == pytest.approx(1.0)


def test_edge_spread_all_nan_frame_reproduces_flat_run_exactly_and_counts_everything():
    close = _close_frame(RETURNS, "2024-01-02", 30)
    hs = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    flat = _run(close, CrossSectionalConfig(cost_bps=5.0, min_names_per_leg=1))
    edge = _run(
        close,
        CrossSectionalConfig(cost_bps=5.0, min_names_per_leg=1, cost_model="edge_spread"),
        hs,
    )
    pd.testing.assert_series_equal(flat.daily_returns, edge.daily_returns)
    assert edge.total_cost == pytest.approx(flat.total_cost)
    first = next(f for f in edge.formations if f.skipped_reason is None)
    # The whole first formation's gross notional (1.0 long + 1.0 short)
    # fell back — unmissably counted, per the field's docstring.
    assert first.edge_flat_fallback_notional == pytest.approx(2.0)


def test_edge_spread_without_half_spread_frame_is_rejected_loudly():
    close = _close_frame(RETURNS, "2024-01-02", 30)
    with pytest.raises(ValueError, match="half_spread"):
        _run(
            close,
            CrossSectionalConfig(cost_bps=5.0, min_names_per_leg=1, cost_model="edge_spread"),
            half_spread=None,
        )


def test_unknown_cost_model_is_rejected_loudly():
    close = _close_frame(RETURNS, "2024-01-02", 30)
    with pytest.raises(ValueError, match="cost_model"):
        _run(close, CrossSectionalConfig(cost_bps=5.0, min_names_per_leg=1, cost_model="edge"))


def test_misaligned_half_spread_frame_fails_validation():
    close = _close_frame(RETURNS, "2024-01-02", 30)
    hs = _half_spread_frame(close, {"A": 0.001, "B": 0.001, "C": 0.001, "D": 0.001}).iloc[:-1]
    with pytest.raises(ValueError, match="half_spread"):
        validate_cross_sectional_data(CrossSectionalData(close=close, half_spread=hs))


def test_screening_reports_turnover_and_fallback_aggregates():
    close = _close_frame(RETURNS, "2024-01-02", 80)  # >= MIN_REPLAY_TRADING_DAYS realized days
    hs = _half_spread_frame(close, {"A": 0.0020, "B": 0.0010, "C": 0.0010, "D": 0.0002})
    hs["A"] = np.nan
    specs = [_spec(pattern_id="s_h5", holding_days=5), _spec(pattern_id="s_h10", holding_days=10)]
    data = CrossSectionalData(close=close, half_spread=hs)

    flat_results = screen_cross_sectional_universe(
        data, specs, CrossSectionalConfig(cost_bps=5.0, min_names_per_leg=1), ALWAYS_MEMBER
    )
    edge_results = screen_cross_sectional_universe(
        data,
        specs,
        CrossSectionalConfig(cost_bps=5.0, min_names_per_leg=1, cost_model="edge_spread"),
        ALWAYS_MEMBER,
    )
    assert len(flat_results) == 2 and len(edge_results) == 2
    for r in flat_results:
        assert r.total_turnover == pytest.approx(2.0)  # one real formation, reformed identically
        assert r.edge_flat_fallback_notional == 0.0
    for r in edge_results:
        assert r.total_turnover == pytest.approx(2.0)
        assert r.edge_flat_fallback_notional == pytest.approx(1.0)  # the NaN'd long ticker


# --- builder: synthetic-spread recovery and contracts -------------------


def _synthetic_spread_ohlc(
    true_spread: float, n_days: int, seed: int, steps_per_day: int = 78, daily_vol: float = 0.02
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Daily OHLC with a KNOWN injected effective spread — the same setup
    spread_estimator.py's documented validation used: efficient mid log-
    price random walk; each observed trade executes at mid * (1 ± S/2);
    the day's OHLC are taken over its observed trades."""
    rng = np.random.default_rng(seed)
    step_vol = daily_vol / np.sqrt(steps_per_day)
    half = true_spread / 2.0
    log_mid = np.log(100.0)
    o, h, l, c = [], [], [], []
    for _ in range(n_days):
        path = log_mid + np.cumsum(rng.normal(0.0, step_vol, steps_per_day))
        log_mid = path[-1]
        sides = rng.choice([-1.0, 1.0], size=steps_per_day)
        trades = np.exp(path) * (1.0 + sides * half)
        o.append(trades[0])
        h.append(trades.max())
        l.append(trades.min())
        c.append(trades[-1])
    index = pd.bdate_range("2015-01-02", periods=n_days)
    return (
        pd.Series(o, index=index),
        pd.Series(h, index=index),
        pd.Series(l, index=index),
        pd.Series(c, index=index),
    )


def _spread_frames(spreads_by_ticker: dict[str, float], n_days: int = 400):
    opens, highs, lows, closes = {}, {}, {}, {}
    for i, (ticker, s) in enumerate(spreads_by_ticker.items()):
        o, h, l, c = _synthetic_spread_ohlc(s, n_days=n_days, seed=100 + i)
        opens[ticker], highs[ticker], lows[ticker], closes[ticker] = o, h, l, c
    return (pd.DataFrame(opens), pd.DataFrame(highs), pd.DataFrame(lows), pd.DataFrame(closes))


def test_builder_recovers_known_synthetic_spreads_at_the_production_window():
    # True FULL spreads of 100bps and 300bps -> true HALF-spreads of 50bps
    # and 150bps. spread_estimator.py's own validation recovered 100/300bps
    # within a few percent even at window=21; at the wider production
    # window the ±50% tolerance here is deliberately loose (this pins
    # "sane recovery", not the estimator's exact bias profile).
    o, h, l, c = _spread_frames({"MID": 0.0100, "WIDE": 0.0300})
    frame = build_edge_half_spread_frame(o, h, l, c, window_days=COST_MODEL_WINDOW_DAYS)

    assert frame.index.equals(c.index) and frame.columns.equals(c.columns)
    med_mid = float(frame["MID"].median())
    med_wide = float(frame["WIDE"].median())
    assert 0.0025 < med_mid < 0.0075  # true half-spread 0.0050
    assert 0.0075 < med_wide < 0.0225  # true half-spread 0.0150
    assert med_wide > med_mid  # ranking by relative cost — the estimator's strongest documented property


def test_builder_output_is_trailing_truncation_invariant():
    # The estimate at row k must depend only on rows <= k: computing it
    # from a frame truncated at k gives the identical value. This is the
    # exact property that makes reading the formation row look-ahead-free.
    o, h, l, c = _spread_frames({"X": 0.0100}, n_days=150)
    full = build_edge_half_spread_frame(o, h, l, c, window_days=63)
    trunc = build_edge_half_spread_frame(
        o.iloc[:100], h.iloc[:100], l.iloc[:100], c.iloc[:100], window_days=63
    )
    np.testing.assert_allclose(
        trunc.iloc[-1].to_numpy(), full.iloc[99].to_numpy(), rtol=1e-12, equal_nan=True
    )


def test_builder_never_emits_non_positive_cells_and_nans_the_warmup():
    o, h, l, c = _spread_frames({"X": 0.0100, "Y": 0.0050}, n_days=120)
    frame = build_edge_half_spread_frame(o, h, l, c, window_days=63)
    values = frame.to_numpy()
    finite = values[np.isfinite(values)]
    assert (finite > 0.0).all()  # NaN, never zero/negative — see the builder's docstring
    # Not enough window in the early rows: no estimate there.
    assert frame.iloc[:30].isna().all().all()
    # And the frame passes the harness's own alignment validation.
    validate_cross_sectional_data(CrossSectionalData(close=c, half_spread=frame))


def test_builder_rejects_misaligned_inputs():
    o, h, l, c = _spread_frames({"X": 0.0100}, n_days=80)
    with pytest.raises(ValueError, match="aligned"):
        build_edge_half_spread_frame(o, h, l, c.iloc[:-1], window_days=21)


# --- intraday per-ticker cost threading ---------------------------------


def _always_long(_window: pd.DataFrame) -> PatternSignal:
    return PatternSignal(direction="long", strength=1.0)


ALWAYS_LONG_SPEC = PatternSpec(
    pattern_id="always_long_test",
    family="test",
    citation="test fixture, not a real citation",
    fire_fn=_always_long,
)


def test_run_pattern_backtest_cost_default_is_the_flat_intraday_rate():
    raw = build_pattern_raw_data(_synthetic_ticker_bars(seed=7, n_days=30))
    default = run_pattern_backtest(ALWAYS_LONG_SPEC, raw)
    explicit = run_pattern_backtest(ALWAYS_LONG_SPEC, raw, cost_bps=INTRADAY_COST_BPS)
    assert [d.equity for d in default.day_results] == [d.equity for d in explicit.day_results]


def test_run_pattern_backtest_higher_cost_strictly_lowers_final_equity():
    raw = build_pattern_raw_data(_synthetic_ticker_bars(seed=7, n_days=30))
    free = run_pattern_backtest(ALWAYS_LONG_SPEC, raw, cost_bps=0.0)
    dear = run_pattern_backtest(ALWAYS_LONG_SPEC, raw, cost_bps=500.0)
    assert dear.day_results[-1].equity < free.day_results[-1].equity


def test_backtest_patterns_for_ticker_threads_cost_through():
    bars = _synthetic_ticker_bars(seed=7, n_days=30)
    free = backtest_patterns_for_ticker(bars, [ALWAYS_LONG_SPEC], cost_bps=0.0)
    dear = backtest_patterns_for_ticker(bars, [ALWAYS_LONG_SPEC], cost_bps=500.0)
    total_free = (1.0 + free["always_long_test"].daily_returns).prod()
    total_dear = (1.0 + dear["always_long_test"].daily_returns).prod()
    assert total_dear < total_free


def test_screen_pattern_universe_per_ticker_costs_match_flat_when_identical():
    bars_by_ticker = {
        "AAA": _synthetic_ticker_bars(seed=1, n_days=30),
        "BBB": _synthetic_ticker_bars(seed=2, n_days=30),
    }
    flat = screen_pattern_universe(bars_by_ticker, patterns=[ALWAYS_LONG_SPEC])
    per_ticker = screen_pattern_universe(
        bars_by_ticker,
        patterns=[ALWAYS_LONG_SPEC],
        cost_bps_by_ticker={"AAA": INTRADAY_COST_BPS, "BBB": INTRADAY_COST_BPS},
    )
    assert len(flat) == len(per_ticker) == 1
    assert flat[0].sharpe_annualized == pytest.approx(per_ticker[0].sharpe_annualized)


def test_screen_pattern_universe_missing_cost_ticker_is_rejected_loudly():
    bars_by_ticker = {
        "AAA": _synthetic_ticker_bars(seed=1, n_days=30),
        "BBB": _synthetic_ticker_bars(seed=2, n_days=30),
    }
    with pytest.raises(ValueError, match="BBB"):
        screen_pattern_universe(
            bars_by_ticker, patterns=[ALWAYS_LONG_SPEC], cost_bps_by_ticker={"AAA": 3.0}
        )
