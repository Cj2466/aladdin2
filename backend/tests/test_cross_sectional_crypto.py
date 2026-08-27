from datetime import date

import numpy as np
import pandas as pd
import pytest

import app.services.research_lab.cross_sectional_crypto as xc
from app.services.research_lab.cross_sectional import (
    CrossSectionalData,
    run_cross_sectional_backtest,
    screen_cross_sectional_universe,
)
from app.services.research_lab.cross_sectional_crypto import (
    CRYPTO_BETA_LOOKBACK_DAYS,
    CRYPTO_CONFOUND_CHECK_DSR,
    CRYPTO_COST_BPS,
    CRYPTO_EXCLUDED,
    CRYPTO_FINANCING_BPS_PER_YEAR,
    CRYPTO_FORMATION_START,
    CRYPTO_HOLDING_DAYS,
    CRYPTO_LEG_WEIGHTING,
    CRYPTO_LOOKBACK_DAYS,
    CRYPTO_LOWVOL_LOOKBACK_DAYS,
    CRYPTO_MARKET_TICKER,
    CRYPTO_MAX_STALE_FRACTION,
    CRYPTO_MIN_DOLLAR_VOLUME,
    CRYPTO_MIN_NAMES_PER_LEG,
    CRYPTO_MOMENTUM_LOOKBACK_DAYS,
    CRYPTO_MOMENTUM_SKIP_DAYS,
    CRYPTO_N_SIGNAL_DEFINITIONS,
    CRYPTO_N_TRIALS,
    CRYPTO_PERIODS_PER_YEAR,
    CRYPTO_PRICE_HISTORY_START,
    CRYPTO_RANK_FRACTION,
    CRYPTO_REVERSAL_LOOKBACK_DAYS,
    CRYPTO_SHORT_BORROW_BPS_PER_YEAR,
    CRYPTO_SKIP_LOOKBACK_DAYS,
    CRYPTO_UNIVERSE,
    build_crypto_family,
    build_dollar_volume,
    build_eligibility,
    build_inverse_vol_basis,
    compute_crypto_factor_exposure,
    default_crypto_config,
    effective_breadth,
    equal_weight_basket_return,
    liquidity_membership,
    signal_crypto_btc_beta,
    signal_crypto_long_run_reversal,
    signal_crypto_low_volatility,
    signal_crypto_momentum,
    signal_crypto_momentum_skip_week,
)
from app.services.research_lab.metrics import sharpe_ratio


def _frame(values_by_ticker: dict[str, list[float]], start: str = "2020-01-01") -> pd.DataFrame:
    """CALENDAR-day indexed, not business-day: this whole family exists
    because crypto has no weekends or holidays, and a fixture on a bdate
    index would quietly test the wrong calendar."""
    n = len(next(iter(values_by_ticker.values())))
    return pd.DataFrame(values_by_ticker, index=pd.date_range(start, periods=n, freq="D"))


def _history(close: pd.DataFrame) -> CrossSectionalData:
    return CrossSectionalData(close=close)


# --- family shape: exactly 28, no more, no fewer ----------------------------


def test_family_is_exactly_28_definitions_and_matches_the_declared_arithmetic():
    family = build_crypto_family()
    assert len(family) == 28
    assert CRYPTO_N_TRIALS == 28
    # 14 signal definitions x 2 holds — DERIVED from the axes, never a typed
    # literal that could drift from them.
    n_signals = (
        len(CRYPTO_MOMENTUM_LOOKBACK_DAYS)
        + len(CRYPTO_SKIP_LOOKBACK_DAYS)
        + len(CRYPTO_REVERSAL_LOOKBACK_DAYS)
        + len(CRYPTO_LOWVOL_LOOKBACK_DAYS)
        + len(CRYPTO_BETA_LOOKBACK_DAYS)
    )
    assert n_signals == 14 == CRYPTO_N_SIGNAL_DEFINITIONS
    assert CRYPTO_N_TRIALS == n_signals * len(CRYPTO_HOLDING_DAYS)


def test_family_covers_five_distinct_mechanisms():
    family = build_crypto_family()
    mechanisms = {xc._mechanism_of(s.pattern_id) for s in family}
    assert mechanisms == {
        "momentum",
        "momentum_skip_week",
        "long_run_reversal",
        "low_volatility",
        "betting_against_beta",
    }
    assert "unknown" not in mechanisms


def test_mechanism_of_does_not_confuse_skip_momentum_with_plain_momentum():
    """The skip variant's pattern_id also starts with 'xc_momentum', so
    prefix order in _mechanism_of is load-bearing."""
    assert xc._mechanism_of("xc_momentum_skip7_l180_h90") == "momentum_skip_week"
    assert xc._mechanism_of("xc_momentum_l180_h90") == "momentum"


def test_every_spec_shares_the_family_lookback_and_declared_shape():
    family = build_crypto_family()
    assert len({s.pattern_id for s in family}) == len(family)
    assert all(s.lookback_days == CRYPTO_LOOKBACK_DAYS for s in family)
    assert CRYPTO_LOOKBACK_DAYS == max(CRYPTO_REVERSAL_LOOKBACK_DAYS) == 730
    assert all(s.portfolio == "long_short" for s in family)
    assert all(s.leg_weighting == CRYPTO_LEG_WEIGHTING == "inverse_vol" for s in family)
    assert all(s.rank_fraction == CRYPTO_RANK_FRACTION for s in family)
    assert all(s.cohort_formation_days is None for s in family)
    assert all(s.citation for s in family)


def test_family_is_close_only_by_design():
    family = build_crypto_family()
    assert not any(
        s.requires_open
        or s.requires_volume
        or s.requires_market_cap
        or s.requires_price_only_close
        or s.requires_shares_outstanding
        for s in family
    )


def test_no_short_holding_period_variants_exist():
    """The standing cost lesson: reformation cost scales with rebalance
    frequency, and at 30bp one-way that is six times harsher than equities."""
    assert min(CRYPTO_HOLDING_DAYS) >= 90
    assert set(CRYPTO_HOLDING_DAYS) == {90, 180}
    assert all(s.holding_days >= 90 for s in build_crypto_family())


def test_leg_weighting_is_fixed_not_swept():
    """FX and commodities swept two weightings and doubled n_trials. This
    family fixes one ex ante, which is why 14 definitions give 28 and not 56."""
    assert CRYPTO_N_TRIALS == CRYPTO_N_SIGNAL_DEFINITIONS * len(CRYPTO_HOLDING_DAYS)
    assert len({s.leg_weighting for s in build_crypto_family()}) == 1


# --- universe and its pre-declared exclusions -------------------------------


def test_no_excluded_ticker_is_in_the_universe():
    assert not (set(CRYPTO_EXCLUDED) & set(CRYPTO_UNIVERSE))
    assert len(CRYPTO_UNIVERSE) == len(set(CRYPTO_UNIVERSE))


def test_every_exclusion_carries_a_stated_reason():
    for ticker, reason in CRYPTO_EXCLUDED.items():
        assert reason and len(reason) > 20, ticker


def test_stablecoins_and_known_broken_feeds_are_excluded():
    for ticker in ("USDT-USD", "USDC-USD", "DAI-USD", "UST-USD"):
        assert ticker in CRYPTO_EXCLUDED
        assert "stablecoin" in CRYPTO_EXCLUDED[ticker]
    for ticker in ("SHIB-USD", "UNI-USD", "APE-USD", "COMP-USD", "GRT-USD", "ANC-USD"):
        assert ticker in CRYPTO_EXCLUDED
    # The real Uniswap ticker IS in the universe; the near-dead namesake is not.
    assert "UNI7083-USD" in CRYPTO_UNIVERSE
    assert "UNI-USD" not in CRYPTO_UNIVERSE


def test_universe_includes_dead_coins_the_survivorship_fix():
    """The whole point: crypto's survivorship bias is fixable for free
    because yfinance retains dead coins, unlike this project's equities."""
    for dead in ("LUNA1-USD", "MATIC-USD", "RNDR-USD", "FTM-USD", "GALA-USD", "FTT-USD"):
        assert dead in CRYPTO_UNIVERSE


def test_market_proxy_is_in_the_universe():
    assert CRYPTO_MARKET_TICKER == "BTC-USD"
    assert CRYPTO_MARKET_TICKER in CRYPTO_UNIVERSE


# --- the 365-day calendar ---------------------------------------------------


def test_config_uses_a_365_day_year_not_252():
    config = default_crypto_config()
    assert config.periods_per_year == 365.0 == CRYPTO_PERIODS_PER_YEAR
    assert config.cost_bps == CRYPTO_COST_BPS == 30.0
    assert config.financing_bps_per_year == CRYPTO_FINANCING_BPS_PER_YEAR == 400.0
    assert CRYPTO_SHORT_BORROW_BPS_PER_YEAR == 800.0
    assert config.min_names_per_leg == CRYPTO_MIN_NAMES_PER_LEG == 5


def test_screening_annualizes_this_family_at_365(monkeypatch):
    """End-to-end: the same replayed return stream must come back annualized
    at 365, not 252. This is the fix actually reaching the family."""
    rng = np.random.default_rng(3)
    # 30 coins so a QUINTILE leg is 6, over min_names_per_leg=5 — the same
    # breadth the real universe supplies (28-71 eligible names).
    n, tickers = 500, [f"C{i}" for i in range(30)]
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rng.normal(0.001, 0.03, size=(n, len(tickers))), axis=0)),
        index=pd.date_range("2021-01-01", periods=n, freq="D"),
        columns=tickers,
    )
    data = CrossSectionalData(close=close, leg_weight_basis=build_inverse_vol_basis(close))
    spec = build_crypto_family()[0]
    spec = type(spec)(**{**spec.__dict__, "lookback_days": 90})
    config = default_crypto_config()
    membership = lambda _t, _d: True

    replay = run_cross_sectional_backtest(data, spec, config, membership)
    assert replay.status == "ok"
    results = screen_cross_sectional_universe(data, [spec], config, membership)
    assert results
    expected = sharpe_ratio(replay.daily_returns, periods_per_year=365)
    at_252 = sharpe_ratio(replay.daily_returns, periods_per_year=252)
    assert results[0].sharpe_annualized == expected
    assert results[0].sharpe_annualized != at_252
    assert results[0].deflated_sharpe.sharpe_net_daily == pytest.approx(expected / np.sqrt(365.0))


def test_lookbacks_are_calendar_days_not_equity_trading_days():
    """Copying the equity families' 63/126/252 across would silently shorten
    every window by 252/365."""
    for axis in (
        CRYPTO_MOMENTUM_LOOKBACK_DAYS,
        CRYPTO_SKIP_LOOKBACK_DAYS,
        CRYPTO_REVERSAL_LOOKBACK_DAYS,
        CRYPTO_LOWVOL_LOOKBACK_DAYS,
        CRYPTO_BETA_LOOKBACK_DAYS,
        CRYPTO_HOLDING_DAYS,
    ):
        assert not ({63, 126, 252, 504, 756, 1260} & set(axis)), axis


# --- signals ----------------------------------------------------------------


def test_momentum_ranks_the_best_trailing_return_highest():
    close = _frame({"A": [100.0] * 50 + [200.0], "B": [100.0] * 51, "C": [100.0] * 50 + [50.0]})
    signal = signal_crypto_momentum(_history(close), lookback_days=51)
    assert signal["A"] > signal["B"] > signal["C"]
    assert signal["A"] == pytest.approx(1.0)
    assert signal["C"] == pytest.approx(-0.5)


def test_reversal_is_exactly_negated_momentum():
    rng = np.random.default_rng(5)
    close = _frame({t: list(100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, 120)))) for t in "ABCDE"})
    history = _history(close)
    momentum = signal_crypto_momentum(history, lookback_days=100)
    reversal = signal_crypto_long_run_reversal(history, lookback_days=100)
    pd.testing.assert_series_equal(reversal, -momentum)


def test_skip_week_ignores_the_most_recent_seven_days():
    """The mechanism's whole content: a coin that collapses in the last week
    must still rank as a past winner under the skip variant, and as a loser
    under plain momentum."""
    n = 60
    # A rises steadily then crashes in the final 7 days; B is flat throughout.
    a = [100.0 + i for i in range(n - 7)] + [40.0] * 7
    b = [100.0] * n
    close = _frame({"A": a, "B": b})
    history = _history(close)

    plain = signal_crypto_momentum(history, lookback_days=n)
    skipped = signal_crypto_momentum_skip_week(history, lookback_days=n)

    assert plain["A"] < plain["B"]  # the crash dominates
    assert skipped["A"] > skipped["B"]  # the crash is excluded
    # The skip signal is exactly the return to 7 days before the end.
    assert skipped["A"] == pytest.approx(a[n - 8] / a[0] - 1.0)


def test_skip_week_default_is_seven_days():
    assert CRYPTO_MOMENTUM_SKIP_DAYS == 7
    n = 40
    close = _frame({"A": [100.0 + i for i in range(n)], "B": [100.0] * n})
    explicit = signal_crypto_momentum_skip_week(_history(close), lookback_days=n, skip_days=7)
    default = signal_crypto_momentum_skip_week(_history(close), lookback_days=n)
    pd.testing.assert_series_equal(default, explicit)


def test_skip_week_rejects_a_lookback_shorter_than_the_skip():
    close = _frame({"A": [100.0] * 20})
    with pytest.raises(ValueError, match="must exceed skip_days"):
        signal_crypto_momentum_skip_week(_history(close), lookback_days=5, skip_days=7)


def test_low_volatility_ranks_the_calmest_coin_highest():
    rng = np.random.default_rng(9)
    n = 120
    calm = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.005, n)))
    wild = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.060, n)))
    close = _frame({"CALM": list(calm), "WILD": list(wild)})
    signal = signal_crypto_low_volatility(_history(close), lookback_days=100)
    assert signal["CALM"] > signal["WILD"]
    # Negated volatility, so both are non-positive.
    assert signal["WILD"] < 0


def test_low_volatility_refuses_a_perfectly_flat_series():
    """A zero-vol window is a stale feed, not the calmest possible market —
    it must not rank as the single best coin."""
    rng = np.random.default_rng(4)
    n = 60
    close = _frame(
        {
            "STALE": [100.0] * n,
            "REAL": list(100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))),
        }
    )
    signal = signal_crypto_low_volatility(_history(close), lookback_days=50)
    assert np.isnan(signal["STALE"])
    assert np.isfinite(signal["REAL"])


def test_btc_beta_is_negated_so_low_beta_ranks_highest():
    rng = np.random.default_rng(13)
    n = 200
    btc_returns = rng.normal(0.0, 0.03, n)
    high = np.cumsum(2.0 * btc_returns)
    low = np.cumsum(0.5 * btc_returns)
    market = np.cumsum(btc_returns)
    close = _frame(
        {
            CRYPTO_MARKET_TICKER: list(100.0 * np.exp(market)),
            "HIGHBETA": list(100.0 * np.exp(high)),
            "LOWBETA": list(100.0 * np.exp(low)),
        }
    )
    signal = signal_crypto_btc_beta(_history(close), lookback_days=180)
    assert signal["LOWBETA"] > signal[CRYPTO_MARKET_TICKER] > signal["HIGHBETA"]
    # BTC's own beta against itself is exactly 1, so its signal is -1.
    assert signal[CRYPTO_MARKET_TICKER] == pytest.approx(-1.0)
    assert signal["HIGHBETA"] == pytest.approx(-2.0, abs=0.05)
    assert signal["LOWBETA"] == pytest.approx(-0.5, abs=0.05)


def test_btc_beta_is_all_nan_when_the_market_proxy_is_absent():
    """A loud, testable contract rather than a silent fallback to some other
    market definition."""
    rng = np.random.default_rng(2)
    close = _frame({t: list(100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, 120)))) for t in "ABC"})
    signal = signal_crypto_btc_beta(_history(close), lookback_days=100)
    assert signal.isna().all()
    assert list(signal.index) == list(close.columns)


@pytest.mark.parametrize(
    "signal_fn",
    [
        lambda h: signal_crypto_momentum(h, lookback_days=100),
        lambda h: signal_crypto_momentum_skip_week(h, lookback_days=100),
        lambda h: signal_crypto_long_run_reversal(h, lookback_days=100),
        lambda h: signal_crypto_low_volatility(h, lookback_days=100),
        lambda h: signal_crypto_btc_beta(h, lookback_days=100),
    ],
)
def test_every_signal_refuses_a_coin_with_too_little_history(signal_fn):
    """A ragged panel means coins are born mid-sample. Every mechanism must
    return NaN for a name whose window is under 80% populated rather than
    rank it on the handful of days it does have."""
    rng = np.random.default_rng(6)
    n = 120
    full = list(100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, n))))
    newborn = [np.nan] * (n - 10) + list(100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, 10))))
    close = _frame(
        {CRYPTO_MARKET_TICKER: full, "OLD": list(np.array(full) * 1.1), "NEWBORN": newborn}
    )
    signal = signal_fn(_history(close))
    assert np.isnan(signal["NEWBORN"])
    assert np.isfinite(signal["OLD"])


# --- dollar volume: the units convention ------------------------------------


def test_dollar_volume_is_the_volume_column_not_price_times_volume():
    """yfinance reports crypto Volume already in USD. Multiplying by price
    would inflate BTC's turnover from ~$40bn/day to ~$2e15/day, and the error
    is invisible in a ranking — which is exactly why it needs a test."""
    close = _frame({"A": [100.0, 200.0], "B": [10.0, 10.0]})
    volume = _frame({"A": [1.0e9, 2.0e9], "B": [5.0e8, 5.0e8]})
    dollar_volume = build_dollar_volume(volume, close)
    pd.testing.assert_frame_equal(dollar_volume, volume)
    assert dollar_volume.loc[dollar_volume.index[0], "A"] == 1.0e9


# --- point-in-time eligibility ----------------------------------------------


def _eligibility_fixture(n: int = 200, seed: int = 21):
    rng = np.random.default_rng(seed)
    close = _frame(
        {
            "LIQUID": list(100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))),
            "THIN": list(100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))),
        }
    )
    volume = _frame(
        {
            "LIQUID": [CRYPTO_MIN_DOLLAR_VOLUME * 10] * n,
            "THIN": [CRYPTO_MIN_DOLLAR_VOLUME / 10] * n,
        }
    )
    return close, volume


def test_eligibility_admits_the_liquid_name_and_refuses_the_thin_one():
    close, volume = _eligibility_fixture()
    eligible = build_eligibility(close, volume)
    assert eligible["LIQUID"].iloc[-1]
    assert not eligible["THIN"].iloc[-1]


def test_eligibility_is_false_before_enough_history_exists():
    close, volume = _eligibility_fixture()
    eligible = build_eligibility(close, volume)
    # min_periods is 60 and the window is shifted, so nothing can qualify
    # before row 61.
    assert not eligible.iloc[:61].to_numpy().any()


def test_eligibility_reads_only_prior_rows():
    """THE point-in-time proof: mutating the FUTURE must not move any earlier
    eligibility flag. Mirrors test_cross_sectional's look-ahead test."""
    close, volume = _eligibility_fixture()
    baseline = build_eligibility(close, volume)

    tampered_close = close.copy()
    tampered_volume = volume.copy()
    cut = 150
    tampered_close.iloc[cut:] = 1.0
    tampered_volume.iloc[cut:] = CRYPTO_MIN_DOLLAR_VOLUME * 1000
    tampered = build_eligibility(tampered_close, tampered_volume)

    # Row `cut` itself is decided from rows < cut, so it too must be unchanged.
    pd.testing.assert_frame_equal(baseline.iloc[: cut + 1], tampered.iloc[: cut + 1])


def test_eligibility_rejects_a_feed_that_goes_stale_mid_sample():
    """The zombie-quote case no static exclusion list can catch."""
    n = 300
    rng = np.random.default_rng(31)
    live = list(100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, n))))
    # Trades normally, then prints the same price every day from row 150.
    zombie = live[:150] + [live[149]] * (n - 150)
    close = _frame({"LIVE": live, "ZOMBIE": zombie})
    volume = _frame({t: [CRYPTO_MIN_DOLLAR_VOLUME * 10] * n for t in ("LIVE", "ZOMBIE")})

    eligible = build_eligibility(close, volume)
    assert eligible["ZOMBIE"].iloc[140]  # still fine before it dies
    assert not eligible["ZOMBIE"].iloc[-1]  # gone once the window is stale
    assert eligible["LIVE"].iloc[-1]
    assert CRYPTO_MAX_STALE_FRACTION == 0.20


def test_eligibility_goes_false_the_day_a_feed_stops_not_a_month_later():
    """Without the same-row price term the flag lingers for up to the full
    liquidity window after a coin dies, because the trailing median still has
    enough prior observations to compute. Measured on the real panel before
    the fix: LUNA1-USD's last price is 2022-10-09 but its flag stayed True to
    2022-11-09."""
    n = 300
    rng = np.random.default_rng(61)
    alive = list(100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, n))))
    dead = alive[:200] + [np.nan] * (n - 200)
    close = _frame({"ALIVE": alive, "DEAD": dead})
    volume = _frame({t: [CRYPTO_MIN_DOLLAR_VOLUME * 10] * n for t in ("ALIVE", "DEAD")})

    eligible = build_eligibility(close, volume)
    assert eligible["DEAD"].iloc[199]  # last day it had a price
    assert not eligible["DEAD"].iloc[200]  # the very next day
    assert not eligible["DEAD"].iloc[200:].to_numpy().any()
    assert eligible["ALIVE"].iloc[-1]


def test_liquidity_membership_answers_false_for_an_unknown_date():
    """'No' rather than 'unknown' — the same convention was_member keeps."""
    close, volume = _eligibility_fixture()
    membership = liquidity_membership(build_eligibility(close, volume))
    assert membership("LIQUID", close.index[-1].date())
    assert not membership("LIQUID", date(1999, 1, 1))
    assert not membership("NOT-A-COIN", close.index[-1].date())


def test_liquidity_membership_matches_the_frame_it_was_built_from():
    close, volume = _eligibility_fixture()
    eligible = build_eligibility(close, volume)
    membership = liquidity_membership(eligible)
    for ts in list(eligible.index)[::17]:
        for ticker in eligible.columns:
            assert membership(ticker, ts.date()) == bool(eligible.loc[ts, ticker])


# --- the ragged panel -------------------------------------------------------


def test_a_dead_coin_does_not_truncate_the_panel_for_everyone_else():
    """The commodity/FX families dropna(how='any') to a common window. Doing
    that here would delete every row after the first coin's death — the exact
    survivorship bias this family exists to avoid."""
    n = 300
    rng = np.random.default_rng(41)
    alive = list(100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, n))))
    dead = alive[:150] + [np.nan] * (n - 150)
    close = _frame({"ALIVE": alive, "DEAD": dead})

    # A ragged panel keeps every row; a common-window one would keep 150.
    assert len(close.dropna(how="all")) == n
    assert len(close.dropna(how="any")) == 150

    eligible = build_eligibility(
        close, _frame({t: [CRYPTO_MIN_DOLLAR_VOLUME * 10] * n for t in ("ALIVE", "DEAD")})
    )
    # The dead coin stops being eligible; the live one carries on.
    assert not eligible["DEAD"].iloc[-1]
    assert eligible["ALIVE"].iloc[-1]


def test_dead_coin_is_ranked_while_alive_and_dropped_after():
    """End-to-end through the harness: the survivorship fix as behaviour, not
    as a claim about the universe list."""
    n = 400
    rng = np.random.default_rng(55)
    tickers = [f"C{i}" for i in range(30)]
    values = {
        t: list(100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.03, n)))) for t in tickers
    }
    values["DEAD"] = list(100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.03, 250)))) + [np.nan] * (
        n - 250
    )
    close = _frame(values)
    data = CrossSectionalData(close=close, leg_weight_basis=build_inverse_vol_basis(close))
    spec = build_crypto_family()[0]
    spec = type(spec)(**{**spec.__dict__, "lookback_days": 90, "holding_days": 30})

    result = run_cross_sectional_backtest(
        data, spec, default_crypto_config(), lambda _t, _d: True
    )
    assert result.status == "ok"
    formed = [f for f in result.formations if f.skipped_reason is None]
    ranked_dead = [f for f in formed if "DEAD" in (f.long_tickers + f.short_tickers)]
    after_death = [f for f in formed if f.date >= close.index[250]]
    assert ranked_dead, "the dead coin was never ranked while it was alive"
    assert all(
        "DEAD" not in (f.long_tickers + f.short_tickers) for f in after_death
    ), "the dead coin was ranked after its price stopped existing"


# --- look-ahead -------------------------------------------------------------


def test_future_prices_cannot_affect_past_formations():
    """Mirrors test_cross_sectional's structural look-ahead test, on this
    family's own specs and calendar."""
    n = 500
    rng = np.random.default_rng(77)
    tickers = [f"C{i}" for i in range(30)]
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.03, size=(n, len(tickers))), axis=0)),
        index=pd.date_range("2021-01-01", periods=n, freq="D"),
        columns=tickers,
    )
    spec = build_crypto_family()[0]
    spec = type(spec)(**{**spec.__dict__, "lookback_days": 90})
    config = default_crypto_config()

    def replay(frame: pd.DataFrame):
        data = CrossSectionalData(close=frame, leg_weight_basis=build_inverse_vol_basis(frame))
        return run_cross_sectional_backtest(data, spec, config, lambda _t, _d: True)

    baseline = replay(close)
    tampered_frame = close.copy()
    tampered_frame.iloc[400:] *= 5.0
    tampered = replay(tampered_frame)

    cut = close.index[400]
    base_before = [f for f in baseline.formations if f.date < cut]
    tamp_before = [f for f in tampered.formations if f.date < cut]
    assert base_before and len(base_before) == len(tamp_before)
    for a, b in zip(base_before, tamp_before, strict=True):
        assert a.date == b.date
        assert a.long_tickers == b.long_tickers
        assert a.short_tickers == b.short_tickers


# --- the confound check -----------------------------------------------------


def test_factor_exposure_strips_a_pure_btc_stream_to_nothing():
    """A stream that IS the market must show beta ~1 and no surviving alpha —
    the case the whole confound check exists to catch."""
    rng = np.random.default_rng(101)
    index = pd.date_range("2021-01-01", periods=400, freq="D")
    btc = pd.Series(rng.normal(0.001, 0.03, len(index)), index=index)
    basket = pd.Series(rng.normal(0.001, 0.03, len(index)), index=index)
    exposure = compute_crypto_factor_exposure("pure_btc", btc.copy(), btc, basket)

    assert exposure.btc_beta == pytest.approx(1.0, abs=1e-6)
    assert exposure.basket_beta == pytest.approx(0.0, abs=1e-6)
    assert exposure.alpha_annualized == pytest.approx(0.0, abs=1e-6)
    assert exposure.factor_neutralized_sharpe == pytest.approx(0.0, abs=1e-6)


def test_factor_exposure_keeps_a_genuinely_orthogonal_alpha():
    rng = np.random.default_rng(103)
    index = pd.date_range("2021-01-01", periods=800, freq="D")
    btc = pd.Series(rng.normal(0.001, 0.03, len(index)), index=index)
    basket = pd.Series(rng.normal(0.001, 0.03, len(index)), index=index)
    # A steady drift with independent noise: real alpha, no factor loading.
    stream = pd.Series(0.002 + rng.normal(0.0, 0.005, len(index)), index=index)
    exposure = compute_crypto_factor_exposure("orthogonal", stream, btc, basket)

    assert abs(exposure.btc_beta) < 0.1
    assert exposure.alpha_annualized > 0.3
    assert exposure.alpha_t_stat > 5
    assert exposure.factor_neutralized_sharpe > 1.0


def test_factor_neutralized_sharpe_is_the_hedged_book_not_the_regression_residual():
    """A REGRESSION FOUND BY THIS FILE'S FIRST RUN. The fit includes an
    intercept, so its residual has mean exactly zero and a Sharpe of ~0 for
    EVERY spec regardless of alpha — reporting that as the factor-neutralized
    Sharpe would have made every result look confounded, including a clean
    one. The reported figure must be the Sharpe of the book with only its
    factor exposures sold off, alpha retained."""
    rng = np.random.default_rng(211)
    index = pd.date_range("2021-01-01", periods=900, freq="D")
    btc = pd.Series(rng.normal(0.001, 0.03, len(index)), index=index)
    basket = pd.Series(rng.normal(0.001, 0.03, len(index)), index=index)
    noise = pd.Series(rng.normal(0.0, 0.004, len(index)), index=index)
    # Genuine alpha PLUS a large deliberate BTC loading.
    stream = 0.0015 + 0.8 * btc + noise
    exposure = compute_crypto_factor_exposure("alpha_plus_beta", stream, btc, basket)

    assert exposure.btc_beta == pytest.approx(0.8, abs=0.02)
    # The raw Sharpe is dominated by the BTC loading; the hedged one is the
    # alpha's own Sharpe, and both must be clearly positive and different.
    hedged = stream - exposure.btc_beta * btc - exposure.basket_beta * basket
    assert exposure.factor_neutralized_sharpe == pytest.approx(
        sharpe_ratio(hedged, periods_per_year=365), rel=1e-9
    )
    assert exposure.factor_neutralized_sharpe > 1.0
    # And it is NOT the mean-zero residual's ~0 Sharpe.
    assert exposure.factor_neutralized_sharpe > 0.5


def test_factor_exposure_annualizes_alpha_at_365():
    rng = np.random.default_rng(107)
    index = pd.date_range("2021-01-01", periods=400, freq="D")
    btc = pd.Series(rng.normal(0.0, 0.03, len(index)), index=index)
    basket = pd.Series(rng.normal(0.0, 0.03, len(index)), index=index)
    stream = pd.Series(0.001, index=index)
    exposure = compute_crypto_factor_exposure("flat", stream, btc, basket)
    assert exposure.alpha_annualized == pytest.approx(0.001 * 365, rel=0.02)


def test_factor_exposure_is_degenerate_safe_on_a_tiny_sample():
    index = pd.date_range("2021-01-01", periods=5, freq="D")
    s = pd.Series(0.01, index=index)
    exposure = compute_crypto_factor_exposure("tiny", s, s, s)
    assert np.isnan(exposure.btc_beta)


def test_equal_weight_basket_respects_the_eligibility_mask():
    close = _frame({"A": [100.0, 110.0, 121.0], "B": [100.0, 90.0, 81.0]})
    all_eligible = pd.DataFrame(True, index=close.index, columns=close.columns)
    only_a = all_eligible.copy()
    only_a["B"] = False

    both = equal_weight_basket_return(close, all_eligible)
    just_a = equal_weight_basket_return(close, only_a)
    assert both.iloc[1] == pytest.approx(0.0)
    assert just_a.iloc[1] == pytest.approx(0.1)


def test_confound_threshold_matches_the_rejected_results_that_motivated_it():
    """Commodities DSR 0.767 and Buyback DSR 0.598 both cleared this bar
    before being explained away by a factor."""
    assert CRYPTO_CONFOUND_CHECK_DSR == 0.5
    assert 0.767 > CRYPTO_CONFOUND_CHECK_DSR
    assert 0.598 > CRYPTO_CONFOUND_CHECK_DSR


# --- diagnostics ------------------------------------------------------------


def test_effective_breadth_is_n_for_independent_series_and_one_for_copies():
    rng = np.random.default_rng(19)
    independent = pd.DataFrame(rng.normal(size=(400, 5)), columns=list("ABCDE"))
    assert effective_breadth(independent) == pytest.approx(5.0, rel=0.15)

    one = rng.normal(size=400)
    copies = pd.DataFrame({c: one for c in "ABCDE"})
    assert effective_breadth(copies) == pytest.approx(1.0, rel=1e-6)


def test_inverse_vol_basis_is_larger_for_the_calmer_coin():
    rng = np.random.default_rng(23)
    n = 200
    close = _frame(
        {
            "CALM": list(100.0 * np.exp(np.cumsum(rng.normal(0, 0.005, n)))),
            "WILD": list(100.0 * np.exp(np.cumsum(rng.normal(0, 0.060, n)))),
        }
    )
    basis = build_inverse_vol_basis(close)
    assert basis["CALM"].iloc[-1] > basis["WILD"].iloc[-1]
    assert basis.iloc[:29].isna().to_numpy().all()  # min_periods respected


# --- production entry point (no network) ------------------------------------


def test_run_crypto_screening_reports_an_empty_panel_without_crashing(monkeypatch):
    class _EmptyProvider:
        def get_daily_ohlcv(self, tickers, start, end):
            return {}, list(tickers)

    summary = xc.run_crypto_screening(
        end=date(2026, 8, 27), provider=_EmptyProvider()  # type: ignore[arg-type]
    )
    assert summary.results == []
    assert summary.n_trials == CRYPTO_N_TRIALS
    assert summary.warnings
    assert "CRYPTO CROSS-SECTIONAL FAMILY" in summary.text


def test_run_crypto_screening_defaults_the_formation_start(monkeypatch):
    """Unlike FX/commodities, this family's default start is a deliberate
    non-trivial date, not 'as soon as the lookback allows'."""
    captured = {}

    class _EmptyProvider:
        def get_daily_ohlcv(self, tickers, start, end):
            captured["start"] = start
            return {}, list(tickers)

    summary = xc.run_crypto_screening(
        end=date(2026, 8, 27), provider=_EmptyProvider()  # type: ignore[arg-type]
    )
    assert captured["start"] == CRYPTO_PRICE_HISTORY_START
    assert summary.formation_start == CRYPTO_FORMATION_START == date(2020, 11, 1)
    # The lookback must warm entirely out of pre-formation data.
    assert (CRYPTO_FORMATION_START - CRYPTO_PRICE_HISTORY_START).days > CRYPTO_LOOKBACK_DAYS
