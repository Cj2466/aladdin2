from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
)
from app.services.research_lab.cross_sectional_ivol import (
    IVOL_HOLDING_HORIZONS_DAYS,
    IVOL_LOOKBACK_DAYS,
    IVOL_RANK_FRACTION,
    ROUND_D1_FAMILY,
    ROUND_D1_PATTERN_CEILING,
    build_point_in_time_market_cap,
    run_round_d1_screening,
    signal_idiosyncratic_volatility,
)


def _frame(values_by_ticker: dict[str, list[float]], start: str = "2023-01-02") -> pd.DataFrame:
    n = len(next(iter(values_by_ticker.values())))
    return pd.DataFrame(values_by_ticker, index=pd.bdate_range(start, periods=n))


# --- family shape guards (same convention as test_cross_sectional_patterns's
# guards on ROUND_C_FAMILY) --------------------------------------------------


def test_family_is_21_definitions_inside_the_hard_ceiling():
    assert len(ROUND_D1_FAMILY) == 21
    assert len(ROUND_D1_FAMILY) <= ROUND_D1_PATTERN_CEILING


def test_family_pattern_ids_are_unique_and_every_spec_is_cited():
    ids = [s.pattern_id for s in ROUND_D1_FAMILY]
    assert len(set(ids)) == len(ids)
    for spec in ROUND_D1_FAMILY:
        assert spec.citation
        assert "Ang" in spec.citation and "Hodrick" in spec.citation
        assert "Bali" in spec.citation and "Cakici" in spec.citation
        assert "Blitz" in spec.citation and "van Vliet" in spec.citation
        assert spec.holding_days > 0
        assert spec.lookback_days > 0
        assert spec.rank_fraction == pytest.approx(IVOL_RANK_FRACTION)


def test_family_is_entirely_value_weighted_and_declares_market_cap():
    # Build D1's whole point: every definition, including the raw-vol
    # robustness split, value-weights its legs — never the old
    # magnitude-weighted default.
    for spec in ROUND_D1_FAMILY:
        assert spec.leg_weighting == "value"
        assert spec.requires_market_cap is True
        assert spec.requires_open is False
        assert spec.requires_volume is False


def test_family_covers_the_18_main_definitions_grid():
    main = [s for s in ROUND_D1_FAMILY if s.pattern_id.startswith("ivol_resid_")]
    assert len(main) == 18
    lookbacks = {s.lookback_days - 1 for s in main}
    holds = {s.holding_days for s in main}
    portfolios = {s.portfolio for s in main}
    assert lookbacks == set(IVOL_LOOKBACK_DAYS)
    assert holds == set(IVOL_HOLDING_HORIZONS_DAYS)
    assert portfolios == {"long_short", "long_universe_hedged"}
    # Full 3 x 3 x 2 grid, no gaps, no duplicates.
    grid = {(s.lookback_days - 1, s.holding_days, s.portfolio) for s in main}
    assert len(grid) == 18


def test_family_covers_the_3_robustness_definitions():
    robust = [s for s in ROUND_D1_FAMILY if s.pattern_id.startswith("ivol_rawvol_")]
    assert len(robust) == 3
    for spec in robust:
        assert spec.lookback_days - 1 == 63  # w=63 only, per the build
        assert spec.portfolio == "long_short"  # long_short only, per the build
    assert {s.holding_days for s in robust} == set(IVOL_HOLDING_HORIZONS_DAYS)


# --- signal_idiosyncratic_volatility: residual IVOL hand-check -------------

# Ground truth computed independently via numpy.polyfit (a different code
# path from this module's own closed-form covariance/variance regression),
# not by running the implementation forward — see the task's own build log
# for the derivation. market_t = mean(X_t, Y_t, Z_t) each day; each series's
# OLS residual (intercept + slope on market) has std(ddof=1) as below.
_X = [0.02, -0.01, 0.015, -0.005]
_Y = [0.01, 0.02, -0.01, 0.03]
_Z = [-0.01, 0.005, 0.02, -0.015]
_IVOL_X = 0.009036961141150643
_IVOL_Y = 0.0031622776601683738
_IVOL_Z = 0.010723805294763607


def _prices_from_returns(returns: list[float], start_price: float = 100.0) -> list[float]:
    prices = [start_price]
    for r in returns:
        prices.append(prices[-1] * (1.0 + r))
    return prices


def test_residual_ivol_hand_check_matches_independent_ols_ground_truth():
    close = _frame(
        {
            "X": _prices_from_returns(_X),
            "Y": _prices_from_returns(_Y),
            "Z": _prices_from_returns(_Z),
        }
    )
    data = CrossSectionalData(close=close)
    signal = signal_idiosyncratic_volatility(data, lookback_days=4, raw_vol=False)

    # Signal is NEGATIVE ivol (top-of-signal == long == lowest vol, matching
    # every other family's "higher signal is more long" convention).
    assert signal["X"] == pytest.approx(-_IVOL_X, abs=1e-9)
    assert signal["Y"] == pytest.approx(-_IVOL_Y, abs=1e-9)
    assert signal["Z"] == pytest.approx(-_IVOL_Z, abs=1e-9)

    # Ranking sanity: Y has the lowest IVOL of the three (0.00316 < 0.00904
    # < 0.01072), so it must rank FIRST (largest, i.e. least negative,
    # signal value) — the AHXZ long candidate.
    ranked = signal.sort_values(ascending=False)
    assert list(ranked.index) == ["Y", "X", "Z"]


def test_raw_vol_robustness_hand_check_matches_plain_std():
    close = _frame({"X": _prices_from_returns(_X), "Y": _prices_from_returns(_Y)})
    data = CrossSectionalData(close=close)
    signal = signal_idiosyncratic_volatility(data, lookback_days=4, raw_vol=True)

    expected_x = float(np.std(_X, ddof=1))
    expected_y = float(np.std(_Y, ddof=1))
    assert signal["X"] == pytest.approx(-expected_x)
    assert signal["Y"] == pytest.approx(-expected_y)
    # raw_vol skips the market regression entirely -- these must NOT equal
    # the residual IVOL values from the test above (different quantities).
    assert signal["X"] != pytest.approx(-_IVOL_X, abs=1e-6)


def test_ivol_refuses_short_history_ipo_artifact():
    n = 60
    full = np.linspace(50, 100, n + 1).tolist()
    sparse = [np.nan] * (n - 5) + list(np.linspace(90, 100, 6))
    close = _frame({"FULL": full, "SPARSE": sparse})
    data = CrossSectionalData(close=close)
    signal = signal_idiosyncratic_volatility(data, lookback_days=n, raw_vol=False)
    assert np.isfinite(signal["FULL"])
    assert np.isnan(signal["SPARSE"])


def test_ivol_raw_vol_also_refuses_short_history():
    n = 60
    full = np.linspace(50, 100, n + 1).tolist()
    sparse = [np.nan] * (n - 5) + list(np.linspace(90, 100, 6))
    close = _frame({"FULL": full, "SPARSE": sparse})
    data = CrossSectionalData(close=close)
    signal = signal_idiosyncratic_volatility(data, lookback_days=n, raw_vol=True)
    assert np.isfinite(signal["FULL"])
    assert np.isnan(signal["SPARSE"])


def test_ivol_zero_for_a_ticker_that_exactly_equals_the_market():
    # A ticker equal to the (equal-weighted) market itself has a perfect,
    # zero-residual fit: IVOL == 0 exactly, the AHXZ-minimum case. Three
    # tickers so TRACK isn't just a literal duplicate of some other single
    # column: TRACK is constructed as (O1 + O2) / 2, which makes
    # mean(TRACK, O1, O2) == TRACK exactly (3T = T+O1+O2 => T=(O1+O2)/2,
    # independently verified: max abs diff market-vs-TRACK is ~3.5e-18,
    # i.e. exact up to floating point).
    rng = np.random.default_rng(3)
    n = 40
    o1 = rng.normal(0.0, 0.01, n)
    o2 = rng.normal(0.0, 0.01, n)
    track = (o1 + o2) / 2.0
    close = _frame(
        {
            "TRACK": _prices_from_returns(track.tolist()),
            "O1": _prices_from_returns(o1.tolist()),
            "O2": _prices_from_returns(o2.tolist()),
        }
    )
    data = CrossSectionalData(close=close)
    signal = signal_idiosyncratic_volatility(data, lookback_days=n, raw_vol=False)
    assert signal["TRACK"] == pytest.approx(0.0, abs=1e-9)


# --- build_point_in_time_market_cap -----------------------------------------


def test_market_cap_forward_fills_from_sparse_share_events_only():
    close = _frame({"A": [10.0, 10.0, 10.0, 10.0, 10.0]})
    idx = close.index
    # Share count known as of day 0 (100) and day 3 (200) only.
    shares = pd.Series([100.0, 200.0], index=[idx[0], idx[3]])
    market_cap, missing = build_point_in_time_market_cap(close, {"A": shares})
    assert missing == []
    expected = pd.Series([1_000.0, 1_000.0, 1_000.0, 2_000.0, 2_000.0], index=idx, name="A")
    pd.testing.assert_series_equal(market_cap["A"], expected, check_names=False)


def test_market_cap_is_nan_before_the_first_known_share_count():
    close = _frame({"A": [10.0, 10.0, 10.0]})
    idx = close.index
    shares = pd.Series([50.0], index=[idx[2]])  # only known as of the LAST day
    market_cap, missing = build_point_in_time_market_cap(close, {"A": shares})
    assert missing == []
    assert market_cap["A"].iloc[0:2].isna().all()
    assert market_cap["A"].iloc[2] == pytest.approx(500.0)


def test_market_cap_reports_tickers_with_no_shares_data_and_leaves_them_nan():
    close = _frame({"A": [10.0, 11.0], "B": [20.0, 21.0]})
    shares = {"A": pd.Series([100.0], index=[close.index[0]])}  # B absent entirely
    market_cap, missing = build_point_in_time_market_cap(close, shares)
    assert missing == ["B"]
    assert market_cap["B"].isna().all()
    assert market_cap["A"].notna().all()


def test_market_cap_future_share_counts_cannot_affect_past_days():
    # Look-ahead-impossibility check, mirroring test_cross_sectional's own
    # "future prices cannot affect past formations" test: perturbing a
    # LATER share-count observation must leave every EARLIER day's market
    # cap bit-identical.
    close = _frame({"A": [10.0] * 10})
    idx = close.index
    shares = pd.Series([100.0, 150.0, 300.0], index=[idx[0], idx[4], idx[8]])
    baseline, _ = build_point_in_time_market_cap(close, {"A": shares})

    perturbed_shares = shares.copy()
    perturbed_shares.iloc[-1] = 999_999.0  # change only the LAST (future-most) observation
    perturbed, _ = build_point_in_time_market_cap(close, {"A": perturbed_shares})

    pd.testing.assert_series_equal(
        baseline["A"].iloc[:8], perturbed["A"].iloc[:8], check_names=False
    )
    assert baseline["A"].iloc[8] != perturbed["A"].iloc[8]  # the changed day itself does differ


def test_market_cap_is_close_times_shares():
    close = _frame({"A": [10.0, 20.0, 30.0]})
    shares = pd.Series([2.0], index=[close.index[0]])
    market_cap, _ = build_point_in_time_market_cap(close, {"A": shares})
    assert list(market_cap["A"]) == pytest.approx([20.0, 40.0, 60.0])


# --- run_round_d1_screening (production entry point, offline) --------------


def test_round_d1_screening_rejects_start_before_membership_coverage():
    with pytest.raises(ValueError, match="predates point-in-time membership"):
        run_round_d1_screening(date(2014, 1, 1), date(2020, 1, 1))


class _FakePriceProvider:
    """Synthetic-data stand-in for YFinanceProvider.get_price_history +
    get_shares_outstanding — no network. Every served ticker gets a real,
    resolvable share-count history except one deliberately excluded name
    (to exercise the tickers_without_shares path end to end)."""

    def __init__(self, tickers_expected_member: list[str], seed: int = 5):
        self.tickers = tickers_expected_member
        self.seed = seed
        self.requested_prices: list[str] | None = None
        self.requested_shares: list[str] | None = None

    def get_price_history(self, tickers, start, end):
        self.requested_prices = list(tickers)
        rng = np.random.default_rng(self.seed)
        index = pd.bdate_range(start, end)
        served = [t for t in tickers if t in self.tickers]
        close = pd.DataFrame(
            {t: 100.0 * np.cumprod(1.0 + rng.normal(0.0003, 0.015, len(index))) for t in served},
            index=index,
        )
        missing = [t for t in tickers if t not in served]
        return close, missing

    def get_shares_outstanding(self, tickers, start, end):
        self.requested_shares = list(tickers)
        index = pd.bdate_range(start, end)
        shares: dict[str, pd.Series] = {}
        missing: list[str] = []
        for t in tickers:
            if t == self.tickers[0]:
                # Deliberately unresolvable, exercising the fallback path.
                missing.append(t)
                continue
            shares[t] = pd.Series([1.0e9], index=[index[0]])
        return shares, missing


_STALWART_MEMBERS = [
    "AAPL", "MSFT", "JPM", "JNJ", "KO", "PG", "XOM", "WMT", "MCD", "HD", "CAT", "MMM",
]


def test_round_d1_screening_runs_end_to_end_against_a_fake_provider():
    provider = _FakePriceProvider(_STALWART_MEMBERS)
    config = CrossSectionalConfig(min_names_per_leg=1)
    results, missing_price, tickers_without_shares = run_round_d1_screening(
        date(2020, 1, 6), date(2024, 12, 31), provider=provider, config=config
    )

    assert provider.requested_prices is not None
    assert len(provider.requested_prices) > 550
    assert set(_STALWART_MEMBERS) <= set(provider.requested_prices)
    assert set(missing_price) == set(provider.requested_prices) - set(_STALWART_MEMBERS)

    # Shares are only fetched for tickers that actually resolved a price.
    assert provider.requested_shares is not None
    assert set(provider.requested_shares) == set(_STALWART_MEMBERS)
    assert tickers_without_shares == [_STALWART_MEMBERS[0]]

    assert results
    for r in results:
        assert r.deflated_sharpe.n_trials == 21  # every definition counted, survivors or not
        assert np.isfinite(r.sharpe_annualized)
        assert r.n_trading_days >= 60
        assert r.n_formations > 0
    sharpes = [r.sharpe_annualized for r in results]
    assert sharpes == sorted(sharpes, reverse=True)
