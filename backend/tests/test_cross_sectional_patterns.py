from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
)
from app.services.research_lab.cross_sectional_patterns import (
    ASSUMED_MEAN_DAILY_TURNOVER,
    ROUND_C_FAMILY,
    ROUND_C_PATTERN_CEILING,
    TURNOVER_NORMALIZATION_WINDOW,
    _turnover_proxy,
    run_round_c_screening,
    signal_52_week_high_nearness,
    signal_capital_gains_overhang,
    signal_component_persistence,
)


def _frame(values_by_ticker: dict[str, list[float]], start: str = "2023-01-02") -> pd.DataFrame:
    n = len(next(iter(values_by_ticker.values())))
    return pd.DataFrame(values_by_ticker, index=pd.bdate_range(start, periods=n))


# --- family shape guards (same convention as test_intraday_patterns's
# guards on PATTERN_FAMILY and test_sp500_membership_history's on the
# vendored data) -----------------------------------------------------------


def test_family_is_30_definitions_inside_the_hard_ceiling():
    assert len(ROUND_C_FAMILY) == 30
    assert len(ROUND_C_FAMILY) <= ROUND_C_PATTERN_CEILING


def test_family_pattern_ids_are_unique_and_every_spec_is_cited():
    ids = [s.pattern_id for s in ROUND_C_FAMILY]
    assert len(set(ids)) == len(ids)
    for spec in ROUND_C_FAMILY:
        assert spec.citation  # every definition traces to a real source
        assert spec.holding_days > 0
        assert spec.lookback_days > 0
        assert 0.0 < spec.rank_fraction <= 0.5


def test_family_declares_its_data_requirements():
    # LPS needs a genuine daily Open; Grinblatt-Han needs Volume. The
    # declarations are what lets the harness fail loudly on Close-only
    # data instead of silently computing garbage.
    for spec in ROUND_C_FAMILY:
        if spec.family == "overnight_intraday_tug_of_war":
            assert spec.requires_open
        if spec.family == "disposition_capital_gains_overhang":
            assert spec.requires_volume
        if spec.family == "disposition_52wk_high":
            assert not spec.requires_open and not spec.requires_volume


def test_family_covers_the_cited_horizons():
    by_family: dict[str, set[int]] = {}
    for spec in ROUND_C_FAMILY:
        by_family.setdefault(spec.family, set()).add(spec.holding_days)
    assert by_family["disposition_52wk_high"] == {21, 63, 126}
    assert by_family["disposition_capital_gains_overhang"] == {21, 63, 126}
    assert by_family["overnight_intraday_tug_of_war"] == {21, 63}


# --- George & Hwang 52-week-high nearness --------------------------------


def test_52_week_high_nearness_hand_check():
    # X: ran to 100 then faded to 80 -> nearness 0.8.
    # Y: sits at its own high -> nearness 1.0.
    n = 252
    x = np.linspace(50, 100, n // 2).tolist() + np.linspace(100, 80, n - n // 2).tolist()
    y = np.linspace(50, 90, n).tolist()
    data = CrossSectionalData(close=_frame({"X": x, "Y": y}))
    signal = signal_52_week_high_nearness(data, lookback_days=252)
    assert signal["X"] == pytest.approx(0.8)
    assert signal["Y"] == pytest.approx(1.0)


def test_52_week_high_refuses_short_history_ipo_artifact():
    # A ticker with only ~3 months of prices would mechanically sit near
    # its own short-window "52-week high" (~1.0) and spuriously rank long
    # — the exact artifact MIN_SIGNAL_OBS_FRACTION exists to refuse.
    n = 252
    old = np.linspace(50, 100, n)
    recent = np.full(n, np.nan)
    recent[-60:] = np.linspace(90, 100, 60)
    data = CrossSectionalData(close=_frame({"OLD": old.tolist(), "IPO": recent.tolist()}))
    signal = signal_52_week_high_nearness(data, lookback_days=252)
    assert np.isfinite(signal["OLD"])
    assert np.isnan(signal["IPO"])


# --- Grinblatt & Han capital-gains overhang ------------------------------


def test_turnover_proxy_is_the_assumed_level_for_constant_volume():
    vol = _frame({"A": [1_000_000.0] * 200})
    proxy = _turnover_proxy(vol)
    # Once the rolling mean has any observations, constant volume divided
    # by its own mean is exactly 1, scaled to the assumed daily turnover.
    assert proxy["A"].iloc[-1] == pytest.approx(ASSUMED_MEAN_DAILY_TURNOVER)
    assert proxy["A"].iloc[TURNOVER_NORMALIZATION_WINDOW] == pytest.approx(ASSUMED_MEAN_DAILY_TURNOVER)


def test_turnover_proxy_stays_inside_probability_bounds():
    rng = np.random.default_rng(5)
    vol = _frame({"A": rng.lognormal(12, 2, 300).tolist(), "B": rng.lognormal(10, 3, 300).tolist()})
    proxy = _turnover_proxy(vol)
    assert (proxy.stack().dropna() >= 0.0).all()
    assert (proxy.stack().dropna() <= 1.0).all()


def test_capital_gains_overhang_hand_check():
    # 100 rows of constant volume (so the proxy is exactly the assumed 1%
    # once its rolling mean warms up) and a flat price of 10 until the last
    # two rows, which are 20 then 40. Reference-price recursion over rows
    # up to (but excluding) the formation row: RP stays 10 through the flat
    # stretch, then the 20-print re-anchors 1% of the float:
    # RP = 0.01*20 + 0.99*10 = 10.1. Overhang = (40 - 10.1) / 40 = 0.7475.
    n = 100
    closes = [10.0] * (n - 2) + [20.0, 40.0]
    vols = [1_000_000.0] * n
    data = CrossSectionalData(close=_frame({"A": closes}), volume=_frame({"A": vols}))
    signal = signal_capital_gains_overhang(data, lookback_days=30)
    assert signal["A"] == pytest.approx((40.0 - 10.1) / 40.0)


def test_capital_gains_overhang_sign_tracks_price_direction():
    n = 400
    rising = np.linspace(50, 150, n).tolist()
    falling = np.linspace(150, 50, n).tolist()
    vols = [1_000_000.0] * n
    data = CrossSectionalData(
        close=_frame({"UP": rising, "DOWN": falling}),
        volume=_frame({"UP": vols, "DOWN": vols}),
    )
    signal = signal_capital_gains_overhang(data, lookback_days=252)
    # A rising price sits above every holder's reference price (unrealized
    # gains -> positive overhang); a falling one sits below it.
    assert signal["UP"] > 0.0
    assert signal["DOWN"] < 0.0


def test_capital_gains_overhang_refuses_short_history():
    n = 400
    sparse = np.full(n, np.nan)
    sparse[-50:] = np.linspace(90, 100, 50)
    vols = [1_000_000.0] * n
    data = CrossSectionalData(
        close=_frame({"FULL": np.linspace(50, 150, n).tolist(), "SPARSE": sparse.tolist()}),
        volume=_frame({"FULL": vols, "SPARSE": vols}),
    )
    signal = signal_capital_gains_overhang(data, lookback_days=252)
    assert np.isfinite(signal["FULL"])
    assert np.isnan(signal["SPARSE"])


# --- Lou, Polk & Skouras overnight/intraday decomposition ----------------


def _gap_vs_drift_data(n: int = 60) -> CrossSectionalData:
    """GAP earns its entire +1%/day overnight (opens 1% above prior close,
    closes flat at its open); DRIFT earns its entire +1%/day intraday
    (opens exactly at prior close, closes 1% above its open)."""
    gap_close = [100.0 * 1.01**i for i in range(n)]
    gap_open = gap_close  # closes at its own open: intraday component 0
    drift_close = [100.0 * 1.01**i for i in range(n)]
    drift_open = [c / 1.01 for c in drift_close]  # opens at prior close
    close = _frame({"GAP": gap_close, "DRIFT": drift_close})
    open_ = _frame({"GAP": gap_open, "DRIFT": drift_open})
    return CrossSectionalData(close=close, open=open_)


def test_component_signals_separate_overnight_from_intraday_earners():
    data = _gap_vs_drift_data()
    overnight = signal_component_persistence(data, component="overnight", lookback_days=21)
    intraday = signal_component_persistence(data, component="intraday", lookback_days=21)

    assert overnight["GAP"] == pytest.approx(0.01)
    assert overnight["DRIFT"] == pytest.approx(0.0)
    assert intraday["GAP"] == pytest.approx(0.0)
    assert intraday["DRIFT"] == pytest.approx(0.01)


def test_components_compound_exactly_to_close_to_close():
    # The decomposition identity (1 + overnight) * (1 + intraday) ==
    # c_t / c_{t-1} is what makes these two components a genuine
    # decomposition rather than two arbitrary features.
    rng = np.random.default_rng(9)
    n = 50
    close = 100.0 * np.cumprod(1.0 + rng.normal(0, 0.01, n))
    open_ = close * (1.0 + rng.normal(0, 0.005, n))
    frame_close = _frame({"A": close.tolist()})
    frame_open = _frame({"A": open_.tolist()})

    overnight = (frame_open / frame_close.shift(1) - 1.0)["A"]
    intraday = (frame_close / frame_open - 1.0)["A"]
    total = frame_close["A"].pct_change()
    combined = (1.0 + overnight) * (1.0 + intraday) - 1.0
    pd.testing.assert_series_equal(combined.dropna(), total.dropna(), check_names=False)


def test_component_signal_refuses_short_history():
    data = _gap_vs_drift_data(n=60)
    sparse_open = data.open.copy()
    sparse_open.loc[sparse_open.index[:-5], "GAP"] = np.nan  # only 5 real opens
    data = CrossSectionalData(close=data.close, open=sparse_open)
    signal = signal_component_persistence(data, component="overnight", lookback_days=21)
    assert np.isnan(signal["GAP"])
    assert np.isfinite(signal["DRIFT"])


# --- run_round_c_screening (production entry point, offline) --------------


def test_round_c_screening_rejects_start_before_membership_coverage():
    with pytest.raises(ValueError, match="predates point-in-time membership"):
        run_round_c_screening(date(2014, 1, 1), date(2020, 1, 1))


class _FakeProvider:
    """Synthetic-data stand-in for YFinanceProvider.get_daily_ohlcv —
    the same aligned three-frame contract, no network."""

    def __init__(self, tickers_expected_member: list[str], seed: int = 17):
        self.tickers = tickers_expected_member
        self.seed = seed
        self.requested: list[str] | None = None

    def get_daily_ohlcv(self, tickers, start, end):
        self.requested = list(tickers)
        rng = np.random.default_rng(self.seed)
        index = pd.bdate_range(start, end)
        served = [t for t in tickers if t in self.tickers]
        close = pd.DataFrame(
            {t: 100.0 * np.cumprod(1.0 + rng.normal(0.0003, 0.015, len(index))) for t in served},
            index=index,
        )
        open_ = close * (1.0 + rng.normal(0.0, 0.004, close.shape))
        volume = pd.DataFrame(
            rng.integers(1_000_000, 5_000_000, close.shape).astype(float),
            index=index,
            columns=close.columns,
        )
        missing = [t for t in tickers if t not in served]
        return {"open": open_, "close": close, "volume": volume}, missing


# Twelve continuously-listed S&P 500 members across the whole test window
# (all present in sp500_membership_history's base universe and never
# removed) — so the real was_member keeps every one eligible at every
# formation date and the pipeline test isolates mechanics, not membership.
_STALWART_MEMBERS = [
    "AAPL", "MSFT", "JPM", "JNJ", "KO", "PG", "XOM", "WMT", "MCD", "HD", "CAT", "MMM",
]


def test_round_c_screening_runs_end_to_end_against_a_fake_provider():
    """Offline end-to-end pipeline check: real universe construction
    (get_universe_over), real membership gating (was_member), the full
    30-definition family, synthetic prices. Small on purpose — the smoke
    test of pipeline correctness, never a source of conclusions."""
    provider = _FakeProvider(_STALWART_MEMBERS)
    config = CrossSectionalConfig(min_names_per_leg=1)
    results, missing = run_round_c_screening(
        date(2020, 1, 6), date(2024, 12, 31), provider=provider, config=config
    )

    # The requested universe came from point-in-time membership over the
    # window — a superset of today's index that includes departed members.
    assert provider.requested is not None
    assert len(provider.requested) > 550
    assert "TWTR" in provider.requested  # departed 2022 — only a union universe asks for it
    assert set(_STALWART_MEMBERS) <= set(provider.requested)
    assert set(missing) == set(provider.requested) - set(_STALWART_MEMBERS)

    assert results  # the pipeline produced sane-shaped output
    for r in results:
        assert r.deflated_sharpe.n_trials == 30  # every definition counted, survivors or not
        assert np.isfinite(r.sharpe_annualized)
        assert r.n_trading_days >= 60
        assert r.n_formations > 0
    sharpes = [r.sharpe_annualized for r in results]
    assert sharpes == sorted(sharpes, reverse=True)
