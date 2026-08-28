"""Tests for the funding-rate carry family. The two load-bearing ones,
per the build's own priorities:

  * test_funding_payment_is_realized_pnl_hand_computed — a hand-computed
    example on CONSTANT prices where the portfolio's entire return must
    be exactly the harvested funding, proving the payment itself is in
    the return construction (not merely a cost to overcome).
  * test_signal_uses_no_future_funding — mutating funding rows AFTER the
    formation row leaves the ranking signal bit-identical, and mutating
    the formation row itself (settled, known cash) does change it.

Everything uses calendar-day indexes: crypto has no weekends, and a
bdate fixture would test the wrong calendar (the sibling crypto test
file's own convention)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional_funding_carry import (
    FUNDING_AVG_WINDOWS_DAYS,
    FUNDING_CARRY_N_TRIALS,
    FUNDING_HOLDING_DAYS,
    FUNDING_RANK_FRACTIONS,
    FundingCarryConfig,
    FundingCarryPanels,
    FundingCarrySpec,
    aggregate_funding_daily,
    binance_symbol_for,
    build_funding_carry_family,
    funding_carry_signal,
    run_funding_carry_backtest,
    screen_funding_carry_family,
)

SYMBOLS = ["AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT"]


def _panels(
    n_days: int = 10,
    start: str = "2021-01-01",
    funding_per_day: dict[str, float] | None = None,
    close_value: float = 100.0,
) -> FundingCarryPanels:
    """A tiny synthetic panel: constant prices, constant per-day funding.
    Constant prices are the point — they make the funding payment the
    ONLY possible source of return."""
    index = pd.date_range(start, periods=n_days, freq="D")
    funding_per_day = funding_per_day or {
        "AAAUSDT": 0.01,  # strongly positive funding: longs pay shorts
        "BBBUSDT": 0.001,
        "CCCUSDT": -0.001,
        "DDDUSDT": -0.01,  # strongly negative: shorts pay longs
    }
    close = pd.DataFrame(close_value, index=index, columns=SYMBOLS)
    volume = pd.DataFrame(1e9, index=index, columns=SYMBOLS)
    funding = pd.DataFrame(
        {s: funding_per_day[s] for s in SYMBOLS}, index=index, dtype=float
    )
    return FundingCarryPanels(
        close=close,
        quote_volume=volume,
        funding_daily=funding,
        coverage={},
        symbols_missing=[],
    )


def _all_eligible(panels: FundingCarryPanels) -> pd.DataFrame:
    return pd.DataFrame(True, index=panels.close.index, columns=panels.close.columns)


def _spec(window: int = 2, holding: int = 2, fraction: float = 0.25) -> FundingCarrySpec:
    return FundingCarrySpec(
        pattern_id=f"test_w{window}_h{holding}", avg_window_days=window,
        holding_days=holding, rank_fraction=fraction,
    )


def _config(**overrides) -> FundingCarryConfig:
    defaults = {
        "cost_bps": 0.0, "min_names_per_leg": 1, "periods_per_year": 365.0,
        "formation_start": date(2021, 1, 3),
    }
    defaults.update(overrides)
    return FundingCarryConfig(**defaults)


# --- pre-declaration ---------------------------------------------------------


def test_family_is_exactly_the_predeclared_enumeration():
    specs = build_funding_carry_family()
    assert len(specs) == FUNDING_CARRY_N_TRIALS == 12
    assert len({s.pattern_id for s in specs}) == 12
    assert FUNDING_CARRY_N_TRIALS == (
        len(FUNDING_AVG_WINDOWS_DAYS) * len(FUNDING_HOLDING_DAYS) * len(FUNDING_RANK_FRACTIONS)
    )
    for s in specs:
        assert s.avg_window_days in FUNDING_AVG_WINDOWS_DAYS
        assert s.holding_days in FUNDING_HOLDING_DAYS
        assert s.rank_fraction in FUNDING_RANK_FRACTIONS


def test_symbol_mapping_rule_and_exceptions():
    assert binance_symbol_for("BTC-USD") == "BTCUSDT"
    assert binance_symbol_for("LUNA1-USD") == "LUNAUSDT"
    assert binance_symbol_for("UNI7083-USD") == "UNIUSDT"


# --- the funding payment IS the return ---------------------------------------


def test_funding_payment_is_realized_pnl_hand_computed():
    """Constant prices, W=2, H=2, one name per leg, zero costs.

    HAND-COMPUTED EXPECTATION. Signal = -mean(funding): DDD (+0.01) is
    highest -> LONG leg; AAA (-0.01 signal) is lowest -> SHORT leg.
      long DDD, one day:  r_net = 0 - (-0.01) = +0.01  (short side pays the long)
      short AAA, one day: -(0 - 0.01)         = +0.01  (the short collects the funding)
      portfolio gross per held day = 0.01 + 0.01 = 0.02, every day.
    With prices constant there is NO other possible source of return: if
    the funding payment were treated as a mere cost (or ignored), every
    daily return would be <= 0."""
    panels = _panels()
    bt = run_funding_carry_backtest(panels, _spec(), _config(), _all_eligible(panels))

    formed = [f for f in bt.formations if f.skipped_reason is None]
    assert formed, "the synthetic panel must actually form"
    for f in formed:
        assert f.long_tickers == ["DDDUSDT"], "most NEGATIVE funding must be the LONG leg"
        assert f.short_tickers == ["AAAUSDT"], "most POSITIVE funding must be the SHORT leg"

    # Formations at rows 2,4,6,8 of 10; realized days are rows 3..9.
    assert len(bt.daily_returns) == 7
    np.testing.assert_allclose(bt.daily_returns.to_numpy(), 0.02, rtol=1e-12)

    # Attribution: ALL funding, NO price.
    np.testing.assert_allclose(bt.total_funding_pnl, 7 * 0.02, rtol=1e-12)
    np.testing.assert_allclose(bt.total_price_pnl, 0.0, atol=1e-15)
    assert bt.total_cost_drag == 0.0


def test_turnover_cost_charged_on_first_realized_day_only():
    """Same book every reformation -> turnover 2.0 once (the initial
    build), 0.0 after; at 10bp one-way the first realized day nets
    0.02 - 2.0 * 0.001 = 0.018 and every later day the full 0.02."""
    panels = _panels()
    bt = run_funding_carry_backtest(
        panels, _spec(), _config(cost_bps=10.0), _all_eligible(panels)
    )
    np.testing.assert_allclose(bt.daily_returns.iloc[0], 0.02 - 2.0 * 10.0 / 10_000.0, rtol=1e-12)
    np.testing.assert_allclose(bt.daily_returns.iloc[1:].to_numpy(), 0.02, rtol=1e-12)
    np.testing.assert_allclose(bt.total_turnover, 2.0, rtol=1e-12)
    np.testing.assert_allclose(bt.total_cost_drag, 2.0 * 10.0 / 10_000.0, rtol=1e-12)


def test_net_equals_price_plus_funding_minus_costs():
    """The attribution identity, on a panel with BOTH price movement and
    funding: sum(daily net) == total_price_pnl + total_funding_pnl -
    total_cost_drag, and the funding component is exactly gross - price
    (identical survivor sets by construction)."""
    panels = _panels()
    rng = np.random.default_rng(7)
    drift = pd.DataFrame(
        rng.normal(0.0, 0.02, size=panels.close.shape),
        index=panels.close.index,
        columns=panels.close.columns,
    )
    panels.close = 100.0 * (1.0 + drift).cumprod()
    bt = run_funding_carry_backtest(
        panels, _spec(), _config(cost_bps=10.0), _all_eligible(panels)
    )
    np.testing.assert_allclose(
        float(bt.daily_returns.sum()),
        bt.total_price_pnl + bt.total_funding_pnl - bt.total_cost_drag,
        rtol=1e-10,
    )
    assert bt.total_funding_pnl != 0.0


# --- look-ahead --------------------------------------------------------------


def test_signal_uses_no_future_funding():
    """Ranking at formation row r may read settled funding THROUGH row r
    and nothing after: mutating any later row leaves the signal
    bit-identical; mutating row r itself (cash settled by the formation
    trade at the day's close) does change it."""
    panels = _panels(n_days=12)
    row = 6
    base = funding_carry_signal(panels.funding_daily, panels.close, row, 5)

    poisoned = panels.funding_daily.copy()
    poisoned.iloc[row + 1 :] = 99.0  # absurd future funding
    after = funding_carry_signal(poisoned, panels.close, row, 5)
    pd.testing.assert_series_equal(base, after)

    on_formation = panels.funding_daily.copy()
    on_formation.iloc[row, on_formation.columns.get_loc("AAAUSDT")] = 99.0
    changed = funding_carry_signal(on_formation, panels.close, row, 5)
    assert changed["AAAUSDT"] != base["AAAUSDT"], (
        "formation-day funding is settled by the close and must be IN the window"
    )


def test_backtest_past_returns_immune_to_future_funding_mutation():
    panels = _panels(n_days=14)
    spec, config = _spec(), _config()
    base = run_funding_carry_backtest(panels, spec, config, _all_eligible(panels))

    poisoned = _panels(n_days=14)
    poisoned.funding_daily.iloc[-1] = -5.0
    mutated = run_funding_carry_backtest(poisoned, spec, config, _all_eligible(poisoned))
    pd.testing.assert_series_equal(
        base.daily_returns.iloc[:-1], mutated.daily_returns.iloc[:-1]
    )


# --- aggregation and coverage ------------------------------------------------


def test_funding_events_bucket_by_utc_day_including_midnight_boundary():
    events = pd.DataFrame(
        {"funding_rate": [0.0001, 0.0002, 0.0003, 0.0004]},
        index=pd.to_datetime(
            [
                "2024-05-01 00:00:00",  # midnight boundary -> belongs to 05-01
                "2024-05-01 08:00:00.013",  # observed live: ms jitter
                "2024-05-01 16:00:00",
                "2024-05-02 00:00:00",  # next day's boundary -> 05-02
            ],
            format="ISO8601",
        ),
    )
    daily = aggregate_funding_daily(events)
    assert daily[pd.Timestamp("2024-05-01")] == pytest.approx(0.0006)
    assert daily[pd.Timestamp("2024-05-02")] == pytest.approx(0.0004)
    assert len(daily) == 2


def test_signal_refuses_thin_coverage_and_unpriced_names():
    panels = _panels(n_days=12)
    # CCC: funding history exists for only the last 2 of a 10-day window.
    panels.funding_daily.iloc[:-2, panels.funding_daily.columns.get_loc("CCCUSDT")] = np.nan
    # BBB: no price at the formation row.
    panels.close.iloc[-1, panels.close.columns.get_loc("BBBUSDT")] = np.nan
    signal = funding_carry_signal(panels.funding_daily, panels.close, len(panels.close) - 1, 10)
    assert np.isnan(signal["CCCUSDT"]), "under-populated funding window must refuse a signal"
    assert np.isnan(signal["BBBUSDT"]), "an unpriced name cannot be traded at formation"
    assert np.isfinite(signal["AAAUSDT"]) and np.isfinite(signal["DDDUSDT"])


def test_thin_universe_skips_formation_flat_not_partial():
    panels = _panels()
    bt = run_funding_carry_backtest(
        panels, _spec(), _config(min_names_per_leg=5), _all_eligible(panels)
    )
    assert all(f.skipped_reason is not None for f in bt.formations)
    assert (bt.daily_returns == 0.0).all(), "a skipped formation holds cash, never a partial book"


# --- screening/persistence contract ------------------------------------------


def test_screening_results_carry_the_persistence_contract_fields():
    """persist_cross_sectional_trial_results requires pattern_id,
    sharpe_annualized, n_trading_days and a deflated_sharpe with
    n_trials/dsr/psr_vs_zero; n_trials must be the PRE-DECLARED 12 even
    when fewer specs are actually screened."""
    panels = _panels(n_days=100)
    rng = np.random.default_rng(11)
    drift = pd.DataFrame(
        rng.normal(0.0, 0.01, size=panels.close.shape),
        index=panels.close.index,
        columns=panels.close.columns,
    )
    panels.close = 100.0 * (1.0 + drift).cumprod()
    specs = [_spec(window=2, holding=7), _spec(window=3, holding=7)]
    specs[1] = FundingCarrySpec(
        pattern_id="test_w3_h7", avg_window_days=3, holding_days=7, rank_fraction=0.25
    )
    results, daily = screen_funding_carry_family(
        panels, specs, _config(formation_start=date(2021, 1, 31))
    )
    assert results, "the synthetic screen must produce results"
    for r in results:
        assert r.pattern_id
        assert isinstance(r.sharpe_annualized, float)
        assert r.n_trading_days >= 60
        assert r.deflated_sharpe.n_trials == FUNDING_CARRY_N_TRIALS == 12
        assert r.deflated_sharpe.psr_vs_zero is None or 0.0 <= r.deflated_sharpe.psr_vs_zero <= 1.0
        assert r.pattern_id in daily
