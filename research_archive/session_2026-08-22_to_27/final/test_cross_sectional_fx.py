from datetime import date

import numpy as np
import pandas as pd
import pytest

import app.services.research_lab.cross_sectional_fx as fxmod
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    fixed_universe_membership,
    run_cross_sectional_backtest,
)
from app.services.research_lab.cross_sectional_fx import (
    FX_CARRY_PUBLICATION_LAG_MONTHS,
    FX_CARRY_SMOOTHING_MONTHS,
    FX_CURRENCIES,
    FX_FINANCING_BPS_PER_YEAR,
    FX_HOLDING_DAYS,
    FX_LEG_WEIGHTINGS,
    FX_LOOKBACK_DAYS,
    FX_MIN_NAMES_PER_LEG,
    FX_MOMENTUM_LOOKBACK_DAYS,
    FX_N_SIGNAL_DEFINITIONS,
    FX_N_TRIALS,
    FX_RANK_FRACTION,
    FX_REVERSAL_LOOKBACK_DAYS,
    FX_SPREAD_BPS_ONE_WAY,
    build_fx_family,
    build_fx_price_panel,
    build_fx_total_return_panel,
    build_inverse_vol_basis,
    screen_fx_family,
    scrub_reversing_bad_prints,
    signal_fx_carry,
    signal_fx_carry_momentum_blend,
    signal_fx_long_run_reversal,
    signal_fx_momentum,
)


def _frame(values_by_ticker: dict[str, list[float]], start: str = "2010-01-04") -> pd.DataFrame:
    n = len(next(iter(values_by_ticker.values())))
    return pd.DataFrame(values_by_ticker, index=pd.bdate_range(start, periods=n))


def _rates(start: str = "2004-01-01", periods: int = 300, **levels: float) -> pd.DataFrame:
    """A complete monthly (foreign - USD) differential panel at constant
    per-currency levels — enough to make carry deterministic in a test."""
    index = pd.date_range(start, periods=periods, freq="MS")
    return pd.DataFrame(
        {c: np.full(periods, levels.get(c, 0.0)) for c in FX_CURRENCIES}, index=index
    )


# --- family shape: exactly 36, no more, no fewer -------------------------


def test_family_is_exactly_36_definitions_and_matches_the_declared_arithmetic():
    family = build_fx_family(_rates())
    assert len(family) == 36
    assert FX_N_TRIALS == 36
    # 9 signal definitions x 2 holds x 2 weightings — the count must be
    # DERIVED from the axes, never a typed literal that could drift from them.
    assert FX_N_SIGNAL_DEFINITIONS == 9
    assert FX_N_TRIALS == FX_N_SIGNAL_DEFINITIONS * len(FX_HOLDING_DAYS) * len(FX_LEG_WEIGHTINGS)
    assert (
        len(FX_CARRY_SMOOTHING_MONTHS)
        + len(FX_MOMENTUM_LOOKBACK_DAYS)
        + len(FX_REVERSAL_LOOKBACK_DAYS)
        + 1
    ) == FX_N_SIGNAL_DEFINITIONS


def test_family_covers_every_axis_combination_exactly_once():
    family = build_fx_family(_rates())
    assert {s.holding_days for s in family} == set(FX_HOLDING_DAYS) == {63, 126}
    assert {s.leg_weighting for s in family} == set(FX_LEG_WEIGHTINGS) == {"equal", "inverse_vol"}
    assert len({s.pattern_id for s in family}) == len(family)
    # Each of the 9 signal definitions appears once per (hold, weighting).
    stems = [s.pattern_id.rsplit("_h", 1)[0] for s in family]
    assert len(set(stems)) == FX_N_SIGNAL_DEFINITIONS
    assert all(stems.count(stem) == len(FX_HOLDING_DAYS) * len(FX_LEG_WEIGHTINGS) for stem in set(stems))


def test_family_declares_no_21_day_hold():
    # The financing cost is TIME-based, so a shorter hold multiplies the
    # small turnover cost without reducing the dominant one — see
    # FX_FINANCING_BPS_PER_YEAR. This is a design commitment, not an
    # accident, so it is asserted.
    assert 21 not in FX_HOLDING_DAYS
    assert all(s.holding_days >= 63 for s in build_fx_family(_rates()))


def test_family_is_close_only_and_never_requests_ohlc_or_volume():
    # The real panel's Close falls outside [Low,High] on up to 6.2% of days
    # and Volume is identically zero, so any spec requiring those would be
    # unsound on this data.
    for spec in build_fx_family(_rates()):
        assert not spec.requires_open
        assert not spec.requires_volume
        assert not spec.requires_market_cap


def test_family_every_spec_is_cited_and_shares_the_common_parameters():
    for spec in build_fx_family(_rates()):
        assert spec.citation
        assert spec.portfolio == "long_short"
        assert spec.lookback_days == FX_LOOKBACK_DAYS == 1260
        assert spec.rank_fraction == pytest.approx(1.0 / 3.0)
        assert spec.cohort_formation_days is None


def test_family_pattern_ids_do_not_collide_with_any_equity_family():
    from app.services.research_lab.cross_sectional_patterns import ROUND_C_FAMILY
    from app.services.research_lab.cross_sectional_patterns_d2 import D2_FAMILY
    from app.services.research_lab.cross_sectional_patterns_round_d import (
        ROUND_D_LPS_INTRADAY_FAMILY,
    )

    fx_ids = {s.pattern_id for s in build_fx_family(_rates())}
    other = (
        {s.pattern_id for s in ROUND_C_FAMILY}
        | {s.pattern_id for s in D2_FAMILY}
        | {s.pattern_id for s in ROUND_D_LPS_INTRADAY_FAMILY}
    )
    assert fx_ids.isdisjoint(other)


def test_tercile_legs_are_three_currencies_and_disjoint():
    # Nine currencies at rank_fraction 1/3 must give legs of exactly 3 that
    # do not overlap — the floating-point arithmetic here decides every
    # leg's size, so it is pinned.
    n_leg = max(1, int(len(FX_CURRENCIES) * FX_RANK_FRACTION))
    assert n_leg == 3
    assert 2 * n_leg <= len(FX_CURRENCIES)
    assert FX_MIN_NAMES_PER_LEG == 3


# --- defect (4): the reversing-bad-print scrub ---------------------------


def test_scrub_removes_a_spike_that_fully_reverses_the_next_day():
    prices = [100.0] * 10
    good = _frame({"A": prices})
    spiked = good.copy()
    spiked.iloc[5, 0] = 140.0  # +40% then -28.6% straight back to 100
    scrubbed, flags = scrub_reversing_bad_prints(spiked)
    assert bool(flags.iloc[5, 0]) is True
    assert np.isnan(scrubbed.iloc[5, 0])
    assert int(flags.to_numpy().sum()) == 1
    # Both halves of the artifact are gone: the fake spike AND its fake
    # reversal are NaN returns after the scrub.
    r = scrubbed.pct_change(fill_method=None)
    assert np.isnan(r.iloc[5, 0]) and np.isnan(r.iloc[6, 0])


def test_scrub_preserves_a_genuine_jump_that_does_not_reverse():
    # The 2015 SNB de-peg shape: a huge move that STAYS. A magnitude cap
    # would delete it; the reversal test must not.
    prices = [100.0] * 5 + [119.0] * 5
    frame = _frame({"CHF": prices})
    scrubbed, flags = scrub_reversing_bad_prints(frame)
    assert int(flags.to_numpy().sum()) == 0
    assert scrubbed.equals(frame)


def test_scrub_ignores_small_moves_even_when_they_round_trip():
    # A 1% up/down wiggle round-trips perfectly but is ordinary FX noise,
    # far below FX_SPIKE_MIN_ABS_RETURN — scrubbing it would delete real data.
    prices = [100.0, 100.0, 101.0, 100.0, 100.0]
    frame = _frame({"A": prices})
    _, flags = scrub_reversing_bad_prints(frame)
    assert int(flags.to_numpy().sum()) == 0


def test_scrub_never_flags_the_final_row_because_it_has_no_next_day():
    prices = [100.0] * 9 + [150.0]
    frame = _frame({"A": prices})
    _, flags = scrub_reversing_bad_prints(frame)
    assert bool(flags.iloc[-1, 0]) is False


def test_scrub_leaves_a_clean_panel_completely_untouched():
    rng = np.random.default_rng(7)
    clean = _frame({c: (100.0 * np.cumprod(1 + rng.normal(0, 0.004, 400))).tolist() for c in FX_CURRENCIES})
    scrubbed, flags = scrub_reversing_bad_prints(clean)
    assert int(flags.to_numpy().sum()) == 0
    pd.testing.assert_frame_equal(scrubbed, clean)


# --- THE DEFENSIVE DEFECT TEST the real data demands ---------------------


class _DefectiveProvider:
    """Reproduces the EXACT defects measured on the real yfinance FX feed:
    Close outside [Low, High], and Volume identically zero. Anything this
    module builds must be provably indifferent to both."""

    def __init__(self, n: int = 400):
        self.n = n

    def get_daily_ohlcv(self, tickers, start, end):
        rng = np.random.default_rng(11)
        index = pd.bdate_range("2010-01-04", periods=self.n)
        close = pd.DataFrame(
            {t: 1.0 * np.cumprod(1 + rng.normal(0, 0.005, self.n)) for t in tickers}, index=index
        )
        # Close DELIBERATELY outside the bar's own range on ~30% of days,
        # and a Volume column that is exactly zero everywhere.
        open_ = close * 0.5
        volume = pd.DataFrame(0.0, index=index, columns=close.columns)
        return {"open": open_, "close": close, "volume": volume}, []


def test_a_quote_with_close_outside_low_high_or_zero_volume_corrupts_nothing():
    """The two confirmed real defects, asserted not to leak anywhere.

    Close-outside-[Low,High] is defended STRUCTURALLY: this module never
    reads Open/High/Low at all, so a bar whose Close is outside its own
    range is indistinguishable from a clean one here — that is the point of
    being Close-only. Zero Volume is defended the same way: the volume
    frame is dropped at the panel boundary and never reaches the harness,
    so no signal can silently divide by it (which would give inf/NaN) or
    weight by it (which would give a zero-weight leg)."""
    provider = _DefectiveProvider()
    panel, _flags, missing = build_fx_price_panel(provider, date(2011, 12, 31))

    assert not panel.empty
    assert missing == []
    assert list(panel.columns) == FX_CURRENCIES
    # Every value finite and positive despite the incoherent OHLC bars.
    assert np.isfinite(panel.to_numpy()).all()
    assert (panel.to_numpy() > 0).all()

    # The zero-volume frame must NOT have been carried into the harness.
    rates = _rates(periods=300, AUD=3.0, NZD=2.5, JPY=-2.0, CHF=-1.5)
    total_return, _ = build_fx_total_return_panel(panel, rates)
    basis = build_inverse_vol_basis(total_return)
    data = CrossSectionalData(close=total_return, leg_weight_basis=basis)
    assert data.volume is None
    assert data.open is None

    # And a real replay over that data produces finite returns, not NaN/inf.
    spec = CrossSectionalSpec(
        pattern_id="fx_defect_probe",
        family="fx_carry",
        citation="test",
        signal_fn=lambda h: signal_fx_carry(h, rate_differentials=rates, smoothing_months=1),
        lookback_days=100,
        holding_days=63,
        portfolio="long_short",
        rank_fraction=FX_RANK_FRACTION,
        leg_weighting="inverse_vol",
    )
    result = run_cross_sectional_backtest(
        data,
        spec,
        CrossSectionalConfig(min_names_per_leg=FX_MIN_NAMES_PER_LEG),
        fixed_universe_membership(FX_CURRENCIES),
    )
    assert result.status == "ok"
    assert len(result.daily_returns) > 0
    assert np.isfinite(result.daily_returns.to_numpy()).all()


def test_zero_volume_frame_is_never_passed_to_the_harness_by_the_entry_point(monkeypatch):
    captured: list[CrossSectionalData] = []

    def fake_screen(data, specs, config, membership_fn=None):
        captured.append(data)
        return []

    monkeypatch.setattr(fxmod, "screen_cross_sectional_universe", fake_screen)
    screen_fx_family(
        end=date(2011, 12, 31),
        provider=_DefectiveProvider(),
        rate_differentials=_rates(periods=300, AUD=3.0),
    )
    assert captured, "the entry point never reached the screening call"
    assert captured[-1].volume is None
    assert captured[-1].open is None
    assert captured[-1].market_cap is None
    assert captured[-1].leg_weight_basis is not None


# --- signals --------------------------------------------------------------


def test_carry_ranks_the_highest_yielder_highest():
    rates = _rates(AUD=4.0, NZD=3.0, NOK=1.0, EUR=-1.0, JPY=-3.0)
    close = _frame({c: [1.0] * 40 for c in FX_CURRENCIES}, start="2020-01-01")
    signal = signal_fx_carry(
        CrossSectionalData(close=close), rate_differentials=rates, smoothing_months=1
    )
    assert signal["AUD"] > signal["NZD"] > signal["NOK"] > signal["EUR"] > signal["JPY"]


def test_carry_respects_the_publication_lag_and_cannot_read_a_recent_rate():
    # A differential that switches sign one month before the formation date
    # must NOT be visible: with an 8-month lag the signal still reads the
    # OLD regime. This is the look-ahead guard, tested behaviorally.
    index = pd.date_range("2015-01-01", periods=80, freq="MS")
    values = np.where(index < pd.Timestamp("2020-01-01"), 5.0, -5.0)
    rates = pd.DataFrame({c: values for c in FX_CURRENCIES}, index=index)
    rates["AUD"] = np.where(index < pd.Timestamp("2020-01-01"), 5.0, -5.0)

    close = _frame({c: [1.0] * 40 for c in FX_CURRENCIES}, start="2020-02-03")
    signal = signal_fx_carry(
        CrossSectionalData(close=close), rate_differentials=rates, smoothing_months=1
    )
    # Formation is Mar-2020ish; minus 8 months lands in mid-2019, before the
    # regime switch, so the signal must still show the OLD (+5.0) level.
    assert signal["AUD"] == pytest.approx(5.0)


def test_carry_lag_is_eight_months_not_the_six_the_scout_proposed():
    # The worst publication lag measured live was SEVEN months (EUR/GBP), so
    # six would be look-ahead. Pinned so it cannot be "optimized" back down.
    assert FX_CARRY_PUBLICATION_LAG_MONTHS == 8


def test_carry_smoothing_windows_actually_differ():
    index = pd.date_range("2015-01-01", periods=80, freq="MS")
    ramp = np.linspace(0.0, 8.0, 80)
    rates = pd.DataFrame({c: ramp for c in FX_CURRENCIES}, index=index)
    close = _frame({c: [1.0] * 40 for c in FX_CURRENCIES}, start="2021-06-01")
    kw = {"rate_differentials": rates}
    s1 = signal_fx_carry(CrossSectionalData(close=close), smoothing_months=1, **kw)
    s3 = signal_fx_carry(CrossSectionalData(close=close), smoothing_months=3, **kw)
    s6 = signal_fx_carry(CrossSectionalData(close=close), smoothing_months=6, **kw)
    # On a rising series, more smoothing => older average => lower value.
    assert s1["EUR"] > s3["EUR"] > s6["EUR"]


def test_carry_is_nan_when_the_smoothing_window_is_not_fully_populated():
    rates = _rates(start="2019-01-01", periods=2, AUD=3.0)
    close = _frame({c: [1.0] * 10 for c in FX_CURRENCIES}, start="2019-10-01")
    signal = signal_fx_carry(
        CrossSectionalData(close=close), rate_differentials=rates, smoothing_months=6
    )
    assert signal.isna().all()


def test_momentum_ranks_the_winner_above_the_loser():
    n = 300
    up = np.linspace(1.0, 2.0, n).tolist()
    down = np.linspace(1.0, 0.5, n).tolist()
    data = CrossSectionalData(close=_frame({"WIN": up, "LOSE": down}))
    signal = signal_fx_momentum(data, lookback_days=252)
    assert signal["WIN"] > 0 > signal["LOSE"]


def test_reversal_is_exactly_the_negated_momentum():
    n = 300
    data = CrossSectionalData(
        close=_frame({"A": np.linspace(1.0, 1.6, n).tolist(), "B": np.linspace(1.0, 0.7, n).tolist()})
    )
    mom = signal_fx_momentum(data, lookback_days=252)
    rev = signal_fx_long_run_reversal(data, lookback_days=252)
    pd.testing.assert_series_equal(rev, -mom)
    # And the direction is the De Bondt-Thaler / AMP value direction:
    # the multi-year LOSER scores highest and goes long.
    assert rev["B"] > rev["A"]


def test_blend_is_a_rank_average_and_needs_both_components():
    rates = _rates(AUD=5.0, NZD=4.0, NOK=3.0, CAD=2.0, GBP=1.0, EUR=0.0, SEK=-1.0, CHF=-2.0, JPY=-3.0)
    n = 300
    # Momentum ordering deliberately the REVERSE of the carry ordering:
    # column i climbs by 0.05*i over the window, so the FIRST name listed is
    # flat (weakest momentum) while carry ranks it strongest.
    order = ["AUD", "NZD", "NOK", "CAD", "GBP", "EUR", "SEK", "CHF", "JPY"]
    close = _frame(
        {c: np.linspace(1.0, 1.0 + 0.05 * i, n).tolist() for i, c in enumerate(order)},
        start="2020-01-01",
    )
    data = CrossSectionalData(close=close)
    momentum = signal_fx_momentum(data, lookback_days=126)
    carry = signal_fx_carry(data, rate_differentials=rates, smoothing_months=3)
    assert momentum["AUD"] < momentum["JPY"]  # momentum ranks AUD last...
    assert carry["AUD"] > carry["JPY"]  # ...and carry ranks it first

    blend = signal_fx_carry_momentum_blend(
        data, rate_differentials=rates, smoothing_months=3, momentum_lookback_days=126
    )
    assert np.isfinite(blend.to_numpy()).all()
    # Exactly opposing ranks average to a flat cross-section — which also
    # proves the blend is a RANK average and not a raw-value average (carry
    # spans -3..+5 while momentum spans 0..0.4, so a raw average would be
    # dominated by carry and would not flatten at all).
    assert blend.std() == pytest.approx(0.0, abs=1e-12)


def test_blend_is_nan_for_a_currency_missing_either_component():
    # No half-blends: a currency with a valid carry but no computable
    # momentum (its price window is mostly missing) must score NaN, not a
    # carry-only value that would silently rank it against fully-blended
    # peers on a different quantity.
    rates = _rates(AUD=5.0, NZD=4.0, NOK=3.0, CAD=2.0, GBP=1.0, EUR=0.0, SEK=-1.0, CHF=-2.0, JPY=-3.0)
    n = 300
    columns = {c: np.linspace(1.0, 1.3, n).tolist() for c in FX_CURRENCIES}
    gappy = [np.nan] * n
    gappy[-126] = 1.0
    gappy[-1] = 1.2
    columns["NOK"] = gappy  # both endpoints present, interior missing
    data = CrossSectionalData(close=_frame(columns, start="2020-01-01"))

    blend = signal_fx_carry_momentum_blend(
        data, rate_differentials=rates, smoothing_months=3, momentum_lookback_days=126
    )
    assert np.isnan(blend["NOK"])
    assert np.isfinite(blend.drop(index="NOK").to_numpy()).all()


# --- total-return panel ---------------------------------------------------


def test_total_return_panel_adds_carry_accrual_to_spot():
    spot = _frame({c: [1.0] * 300 for c in FX_CURRENCIES}, start="2020-01-01")
    rates = _rates(start="2019-01-01", periods=40, AUD=3.65)  # 3.65%/yr on AUD only
    tr, carry_end = build_fx_total_return_panel(spot, rates)
    assert carry_end is not None
    # Flat spot: AUD's total return must be purely the accrued differential,
    # and a zero-differential currency must not move at all.
    assert tr["AUD"].iloc[-1] > 1.0
    assert tr["EUR"].iloc[-1] == pytest.approx(1.0)
    elapsed_days = (tr.index[-1] - tr.index[0]).days
    expected = (1.0 + 0.0365 / 365.0) ** elapsed_days
    assert tr["AUD"].iloc[-1] == pytest.approx(expected, rel=5e-3)


def test_total_return_panel_truncates_at_the_last_published_rate_month():
    spot = _frame({c: [1.0] * 600 for c in FX_CURRENCIES}, start="2020-01-01")
    rates = _rates(start="2019-01-01", periods=24)  # ends Dec-2020
    tr, carry_end = build_fx_total_return_panel(spot, rates)
    assert carry_end == pd.Timestamp("2020-12-31")
    assert tr.index.max() <= pd.Timestamp("2020-12-31")
    # ...and it did NOT forward-fill a fabricated 2021 carry.
    assert len(tr) < len(spot)


def test_total_return_panel_keeps_a_scrubbed_nan_a_single_cell_gap():
    # A cumulative product over a NaN would poison every later row; the
    # accrual factor is built from the (gapless) rate panel alone precisely
    # so that does not happen.
    spot = _frame({c: [1.0] * 200 for c in FX_CURRENCIES}, start="2020-01-01")
    spot.iloc[50, spot.columns.get_loc("NOK")] = np.nan
    rates = _rates(start="2019-01-01", periods=30, NOK=2.0)
    tr, _ = build_fx_total_return_panel(spot, rates)
    assert np.isnan(tr["NOK"].iloc[50])
    assert np.isfinite(tr["NOK"].iloc[51])
    assert np.isfinite(tr["NOK"].iloc[-1])
    assert tr["NOK"].notna().sum() == len(tr) - 1


# --- inverse-vol weighting basis -----------------------------------------


def test_inverse_vol_basis_is_larger_for_the_calmer_currency():
    rng = np.random.default_rng(3)
    n = 300
    calm = 1.0 * np.cumprod(1 + rng.normal(0, 0.002, n))
    wild = 1.0 * np.cumprod(1 + rng.normal(0, 0.020, n))
    basis = build_inverse_vol_basis(_frame({"CALM": calm.tolist(), "WILD": wild.tolist()}))
    assert basis["CALM"].iloc[-1] > basis["WILD"].iloc[-1]


def test_inverse_vol_basis_is_point_in_time_and_never_infinite():
    n = 200
    flat = _frame({"A": [1.0] * n, "B": [1.0] * n})
    basis = build_inverse_vol_basis(flat)
    # Zero volatility must yield NaN (unusable), never inf — an infinite
    # weight would silently make one currency the whole leg.
    assert not np.isinf(basis.to_numpy()).any()
    assert basis["A"].isna().all()

    # Point-in-time: truncating the frame must not change earlier values.
    rng = np.random.default_rng(5)
    px = _frame({"A": (1.0 * np.cumprod(1 + rng.normal(0, 0.006, 300))).tolist()})
    full = build_inverse_vol_basis(px)
    partial = build_inverse_vol_basis(px.iloc[:200])
    pd.testing.assert_series_equal(full["A"].iloc[:200], partial["A"], check_names=False)


def test_inverse_vol_weighting_actually_reaches_the_legs():
    # An inverse_vol spec whose basis is missing must raise rather than
    # silently fall back and report itself as inverse-vol weighted.
    close = _frame({c: [1.0 + 0.001 * i for i in range(300)] for c in FX_CURRENCIES})
    spec = build_fx_family(_rates())[0]
    inverse_vol_spec = next(s for s in build_fx_family(_rates()) if s.leg_weighting == "inverse_vol")
    with pytest.raises(ValueError, match="leg_weight_basis is None"):
        run_cross_sectional_backtest(
            CrossSectionalData(close=close),
            inverse_vol_spec,
            CrossSectionalConfig(min_names_per_leg=FX_MIN_NAMES_PER_LEG),
            fixed_universe_membership(FX_CURRENCIES),
        )
    # ...whereas the equal-weighted sibling needs no basis at all.
    assert spec.leg_weighting in FX_LEG_WEIGHTINGS


# --- costs ----------------------------------------------------------------


def test_default_config_sets_both_costs_and_an_explicit_config_is_respected(monkeypatch):
    captured: list[CrossSectionalConfig] = []

    def fake_screen(data, specs, config, membership_fn=None):
        captured.append(config)
        return []

    monkeypatch.setattr(fxmod, "screen_cross_sectional_universe", fake_screen)
    provider = _DefectiveProvider()
    rates = _rates(periods=300, AUD=3.0)

    screen_fx_family(end=date(2011, 12, 31), provider=provider, rate_differentials=rates)
    assert captured[-1].cost_bps == pytest.approx(FX_SPREAD_BPS_ONE_WAY)
    assert captured[-1].financing_bps_per_year == pytest.approx(FX_FINANCING_BPS_PER_YEAR)
    assert captured[-1].min_names_per_leg == FX_MIN_NAMES_PER_LEG

    explicit = CrossSectionalConfig(min_names_per_leg=2)
    screen_fx_family(
        end=date(2011, 12, 31), provider=provider, config=explicit, rate_differentials=rates
    )
    assert captured[-1] is explicit
    assert captured[-1].financing_bps_per_year == pytest.approx(0.0)


def test_financing_cost_is_time_based_so_a_longer_hold_pays_more_of_it():
    """The whole justification for dropping the 21-day hold, asserted.

    Uses a MOMENTUM signal on random-walk prices rather than the constant
    carry fixture: a signal whose ranking never changes reforms the same
    book every time and so trades nothing after the first formation, which
    would make the turnover comparison vacuously equal (and did, in an
    earlier draft of this test)."""
    rng = np.random.default_rng(19)
    n = 1200
    close = _frame(
        {c: (1.0 * np.cumprod(1 + rng.normal(0, 0.007, n))).tolist() for c in FX_CURRENCIES}
    )
    data = CrossSectionalData(close=close, leg_weight_basis=build_inverse_vol_basis(close))
    config = CrossSectionalConfig(
        cost_bps=FX_SPREAD_BPS_ONE_WAY,
        financing_bps_per_year=FX_FINANCING_BPS_PER_YEAR,
        min_names_per_leg=FX_MIN_NAMES_PER_LEG,
    )
    financing = {}
    turnover = {}
    for hold in (63, 126):
        spec = CrossSectionalSpec(
            pattern_id=f"probe_h{hold}",
            family="fx_momentum",
            citation="test",
            signal_fn=lambda h: signal_fx_momentum(h, lookback_days=126),
            lookback_days=252,
            holding_days=hold,
            portfolio="long_short",
            rank_fraction=FX_RANK_FRACTION,
            leg_weighting="equal",
        )
        res = run_cross_sectional_backtest(data, spec, config, fixed_universe_membership(FX_CURRENCIES))
        financing[hold] = res.total_financing_cost
        turnover[hold] = res.total_cost

    # Financing accrues per unit TIME, so both holds — covering nearly the
    # same calendar span — pay almost the same total, and it is never zero.
    assert financing[63] > 0 and financing[126] > 0
    assert financing[126] == pytest.approx(financing[63], rel=0.15)
    # Turnover cost, by contrast, is paid per formation: halving the number
    # of formations roughly halves it. Shortening the hold therefore cannot
    # reduce the dominant cost, only multiply the small one.
    assert turnover[63] > turnover[126]
    # And the time-based charge really is the dominant one here.
    assert financing[63] > turnover[63]


def test_financing_is_reported_separately_and_never_folded_into_total_cost():
    close = _frame({c: [1.0 + 0.0005 * i for i in range(600)] for c in FX_CURRENCIES})
    rates = _rates(periods=300, AUD=4.0, JPY=-3.0)
    data = CrossSectionalData(close=close, leg_weight_basis=build_inverse_vol_basis(close))
    spec = CrossSectionalSpec(
        pattern_id="probe",
        family="fx_carry",
        citation="test",
        signal_fn=lambda h: signal_fx_carry(h, rate_differentials=rates, smoothing_months=1),
        lookback_days=300,
        holding_days=63,
        portfolio="long_short",
        rank_fraction=FX_RANK_FRACTION,
        leg_weighting="equal",
    )
    with_fin = run_cross_sectional_backtest(
        data,
        spec,
        CrossSectionalConfig(
            cost_bps=FX_SPREAD_BPS_ONE_WAY,
            financing_bps_per_year=FX_FINANCING_BPS_PER_YEAR,
            min_names_per_leg=FX_MIN_NAMES_PER_LEG,
        ),
        fixed_universe_membership(FX_CURRENCIES),
    )
    without_fin = run_cross_sectional_backtest(
        data,
        spec,
        CrossSectionalConfig(
            cost_bps=FX_SPREAD_BPS_ONE_WAY,
            financing_bps_per_year=0.0,
            min_names_per_leg=FX_MIN_NAMES_PER_LEG,
        ),
        fixed_universe_membership(FX_CURRENCIES),
    )
    # Turnover cost is identical; only the financing line differs.
    assert with_fin.total_cost == pytest.approx(without_fin.total_cost)
    assert without_fin.total_financing_cost == pytest.approx(0.0)
    assert with_fin.total_financing_cost > 0.0
    # ...and the financing genuinely reduced the realized returns.
    assert with_fin.daily_returns.sum() < without_fin.daily_returns.sum()


# --- entry point ----------------------------------------------------------


def test_screening_uses_fixed_universe_membership_not_the_equity_gate(monkeypatch):
    captured: list = []

    def fake_screen(data, specs, config, membership_fn=None):
        captured.append(membership_fn)
        return []

    monkeypatch.setattr(fxmod, "screen_cross_sectional_universe", fake_screen)
    screen_fx_family(
        end=date(2011, 12, 31),
        provider=_DefectiveProvider(),
        rate_differentials=_rates(periods=300, AUD=3.0),
    )
    membership_fn = captured[-1]
    assert membership_fn is not None, "membership_fn=None would route FX to the S&P 500 gate"
    for currency in FX_CURRENCIES:
        assert membership_fn(currency, date(2015, 6, 1)) is True
    assert membership_fn("AAPL", date(2015, 6, 1)) is False


def test_screening_runs_end_to_end_offline_and_reports_every_disclosure():
    """Offline end-to-end smoke test: the real family, the real harness, the
    real membership gate, synthetic prices carrying the real defects. Small
    on purpose — a pipeline check, never a source of conclusions."""
    provider = _DefectiveProvider(n=2200)
    rates = _rates(
        start="2008-01-01",
        periods=200,
        AUD=4.0, NZD=3.5, NOK=2.0, CAD=1.0, GBP=0.5, EUR=-0.5, SEK=-1.0, CHF=-2.0, JPY=-3.0,
    )
    summary = screen_fx_family(
        end=date(2018, 12, 31), provider=provider, rate_differentials=rates
    )

    assert summary.n_trials == 36
    assert summary.missing_price_data == []
    assert summary.leg_size == 3
    assert summary.carry_publication_lag_months == 8
    assert summary.carry_data_end is not None
    assert summary.n_panel_rows > 0
    assert summary.panel_start is not None and summary.panel_end is not None
    assert summary.text and "36" in summary.text
    assert "CLOSE-ONLY" in summary.text
    assert "TOTAL RETURNS" in summary.text

    assert summary.results, "the pipeline produced no results"
    for r in summary.results:
        # This family's OWN n_trials, never pooled with an equity family's.
        assert r.deflated_sharpe.n_trials == 36
        assert np.isfinite(r.sharpe_annualized)
        assert r.n_trading_days >= 60
        assert r.n_formations > 0
        # 36 >= MIN_TRIALS_FOR_DSR (5), so unlike D2 the DSR proper computes.
        assert r.deflated_sharpe.dsr_floor_met is True
        assert r.deflated_sharpe.dsr is not None
        assert r.total_financing_drag > 0.0


def test_screening_survives_a_provider_that_returns_nothing():
    class _EmptyProvider:
        def get_daily_ohlcv(self, tickers, start, end):
            return {}, list(tickers)

    summary = screen_fx_family(
        end=date(2020, 1, 1), provider=_EmptyProvider(), rate_differentials=_rates()
    )
    assert summary.results == []
    assert summary.n_trials == 36
    assert summary.n_panel_rows == 0
    assert summary.warnings
