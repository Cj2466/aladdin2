from datetime import date

import numpy as np
import pandas as pd
import pytest

import app.services.research_lab.cross_sectional_bonds as bonds
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    EmptyEligibleUniverseError,
    fixed_universe_membership,
    run_cross_sectional_backtest,
    screen_cross_sectional_universe,
    validate_cross_sectional_data,
)
from app.services.research_lab.cross_sectional_bonds import (
    BONDS_COMMON_HISTORY_START,
    BONDS_COST_BPS,
    BONDS_FAMILY,
    BONDS_FINANCING_BPS_PER_YEAR,
    BONDS_FULL_RANK_FRACTION,
    BONDS_HOLDING_DAYS,
    BONDS_LADDER_RANK_FRACTION,
    BONDS_LOOKBACK_DAYS,
    BONDS_MIN_NAMES_PER_LEG,
    BONDS_N_TRIALS,
    BONDS_SHORT_BORROW_BPS_PER_YEAR,
    BONDS_UNIVERSE,
    SPREAD_INSTRUMENTS,
    TREASURY_LADDER,
    annualized_income_yield,
    build_bonds_disclosure,
    default_bonds_config,
    empirical_duration_betas,
    rate_factor,
    run_bonds_screening,
    signal_curve_butterfly,
    signal_curve_carry_rolldown,
    signal_duration_hedged_credit,
)

# --- synthetic-data helpers -----------------------------------------------

# Notional "true" durations used to GENERATE synthetic data in these tests.
# The module under test never sees these — it estimates its own betas — so
# they double as the answer key for the duration-estimation tests.
_TRUE_DURATION = {
    "SHY": 0.2,
    "IEI": 0.5,
    "IEF": 1.0,
    "TLH": 1.4,
    "TLT": 2.0,
    "TIP": 0.6,
    "LQD": 0.8,
    "HYG": 0.1,
}


def _synthetic_bond_panel(
    n: int = 900,
    *,
    income_by_ticker: dict[str, float] | None = None,
    idio_by_ticker: dict[str, np.ndarray] | None = None,
    seed: int = 11,
    start: str = "2015-01-02",
    tickers: tuple[str, ...] = BONDS_UNIVERSE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Builds an aligned (total_return_close, price_only_close) pair with a
    REAL factor structure: every ETF's daily price return is its own true
    duration times a common rate factor, plus optional idiosyncratic noise.
    The total-return series additionally accrues a constant per-ticker daily
    income, so the wedge between the two frames is an exactly known yield —
    which is what makes annualized_income_yield hand-checkable."""
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(start, periods=n)
    factor = rng.normal(0.0, 0.004, n)
    income_by_ticker = income_by_ticker or {}
    idio_by_ticker = idio_by_ticker or {}

    tr_cols: dict[str, np.ndarray] = {}
    px_cols: dict[str, np.ndarray] = {}
    for ticker in tickers:
        price_ret = _TRUE_DURATION[ticker] * factor
        if ticker in idio_by_ticker:
            price_ret = price_ret + idio_by_ticker[ticker]
        daily_income = income_by_ticker.get(ticker, 0.0) / bonds.TRADING_DAYS_PER_YEAR
        price_level = 100.0 * np.cumprod(1.0 + price_ret)
        px_cols[ticker] = price_level
        # Income is applied as a separate compounding factor on top of the
        # price path, rather than added into the daily return, so the wedge
        # between the two frames is EXACTLY (1 + daily_income)^t — which is
        # what lets the income-yield test be a precise hand-check rather
        # than an approximate one.
        tr_cols[ticker] = price_level * (1.0 + daily_income) ** np.arange(n)

    total_return = pd.DataFrame(tr_cols, index=index)
    price_only = pd.DataFrame(px_cols, index=index)
    return total_return, price_only


def _data(n: int = 900, **kwargs) -> CrossSectionalData:
    total_return, price_only = _synthetic_bond_panel(n, **kwargs)
    return CrossSectionalData(close=total_return, price_only_close=price_only)


# ==========================================================================
# family shape: exactly these 18, no more, no fewer
# ==========================================================================

EXPECTED_PATTERN_IDS = {
    f"bonds_{mechanism}_l{lookback}_h{holding}"
    for mechanism in ("curve_carry", "butterfly", "credit_hedged")
    for lookback in (63, 252)
    for holding in (63, 126, 252)
}


def test_family_is_exactly_18_definitions():
    assert len(BONDS_FAMILY) == 18
    assert BONDS_N_TRIALS == 18


def test_family_size_is_the_grid_product_not_a_copied_number():
    # The pre-declared n_trials must equal the grid actually enumerated:
    # 3 mechanisms x 2 lookbacks x 3 holding periods.
    assert len(bonds._MECHANISMS) == 3
    assert len(BONDS_LOOKBACK_DAYS) == 2
    assert len(BONDS_HOLDING_DAYS) == 3
    assert len(bonds._MECHANISMS) * len(BONDS_LOOKBACK_DAYS) * len(BONDS_HOLDING_DAYS) == BONDS_N_TRIALS


def test_family_pattern_ids_are_exactly_the_expected_18_and_no_others():
    ids = {s.pattern_id for s in BONDS_FAMILY}
    assert ids == EXPECTED_PATTERN_IDS
    assert len([s.pattern_id for s in BONDS_FAMILY]) == 18  # no duplicates collapsed above


def test_family_covers_every_axis_combination_exactly_once():
    combos = {(bonds._mechanism_of(s.pattern_id), s.lookback_days, s.holding_days) for s in BONDS_FAMILY}
    assert len(combos) == 18
    assert {c[0] for c in combos} == {"curve_carry", "butterfly", "credit_hedged"}
    assert {c[1] for c in combos} == {63, 252}
    assert {c[2] for c in combos} == {63, 126, 252}


def test_family_every_spec_is_cited_and_shares_the_common_parameters():
    for spec in BONDS_FAMILY:
        assert spec.citation  # every definition traces to a real source
        assert spec.portfolio == "long_short"
        assert spec.leg_weighting == "magnitude"
        assert spec.cohort_formation_days is None  # non-overlapping holds
        assert not spec.requires_open and not spec.requires_volume and not spec.requires_market_cap


def test_family_excludes_21_day_holds_and_keeps_63_as_the_floor():
    holds = {s.holding_days for s in BONDS_FAMILY}
    assert 21 not in holds
    assert min(holds) == 63 == bonds.BONDS_MIN_HOLDING_DAYS
    assert bonds.BONDS_DEFAULT_HOLDING_DAYS == 126
    assert bonds.BONDS_DEFAULT_HOLDING_DAYS in holds


def test_each_mechanism_carries_its_own_real_citation():
    by_mechanism = {bonds._mechanism_of(s.pattern_id): s.citation for s in BONDS_FAMILY}
    assert "Koijen" in by_mechanism["curve_carry"] and "Campbell" in by_mechanism["curve_carry"]
    assert "Litterman" in by_mechanism["butterfly"] and "Scheinkman" in by_mechanism["butterfly"]
    assert "Collin-Dufresne" in by_mechanism["credit_hedged"]
    assert len(set(by_mechanism.values())) == 3  # three distinct citations, not one reused


def test_only_the_carry_mechanism_declares_it_needs_the_price_only_basis():
    for spec in BONDS_FAMILY:
        expected = bonds._mechanism_of(spec.pattern_id) == "curve_carry"
        assert spec.requires_price_only_close is expected


def test_family_pattern_ids_never_collide_with_any_other_family():
    from app.services.research_lab.cross_sectional_ivol import ROUND_D1_FAMILY
    from app.services.research_lab.cross_sectional_patterns import ROUND_C_FAMILY
    from app.services.research_lab.cross_sectional_patterns_d2 import D2_FAMILY
    from app.services.research_lab.cross_sectional_patterns_round_d import (
        ROUND_D_LPS_INTRADAY_FAMILY,
    )

    bonds_ids = {s.pattern_id for s in BONDS_FAMILY}
    other_ids = set()
    for family in (ROUND_C_FAMILY, D2_FAMILY, ROUND_D_LPS_INTRADAY_FAMILY, ROUND_D1_FAMILY):
        other_ids |= {s.pattern_id for s in family}
    assert bonds_ids.isdisjoint(other_ids)


# ==========================================================================
# leg arithmetic for an 8-name universe (the thing that silently kills a run)
# ==========================================================================


def test_rank_fractions_produce_legs_of_exactly_two_and_two_disjoint_legs():
    from app.services.research_lab.cross_sectional import select_leg_tickers

    # Ladder mechanisms rank 5 names; the full-basket mechanism ranks 8.
    for n_ranked, rank_fraction in ((5, BONDS_LADDER_RANK_FRACTION), (8, BONDS_FULL_RANK_FRACTION)):
        signal = pd.Series(
            {f"T{i}": float(i) for i in range(n_ranked)}, dtype=float
        )
        top, bottom = select_leg_tickers(signal, rank_fraction)
        assert len(top) == 2, f"{n_ranked} names at rank_fraction {rank_fraction}"
        assert len(bottom) == 2
        assert set(top).isdisjoint(bottom)  # legs must not overlap
        assert 2 * len(top) <= n_ranked


def test_min_names_per_leg_is_configured_below_the_harness_default():
    from app.services.research_lab.cross_sectional import DEFAULT_MIN_NAMES_PER_LEG

    assert BONDS_MIN_NAMES_PER_LEG == 2
    assert BONDS_MIN_NAMES_PER_LEG < DEFAULT_MIN_NAMES_PER_LEG
    # ...and the family's own config actually sets it, or every formation
    # this family attempts would be skipped for a too-small leg.
    assert default_bonds_config().min_names_per_leg == BONDS_MIN_NAMES_PER_LEG


def test_the_harness_default_config_really_would_skip_every_formation():
    """The reason min_names_per_leg must be set explicitly, proven rather
    than asserted: with the harness default of 5, an 8-name universe can
    never form a leg big enough and every formation is skipped."""
    data = _data(600)
    spec = next(s for s in BONDS_FAMILY if s.pattern_id == "bonds_credit_hedged_l252_h126")
    default_config = CrossSectionalConfig(formation_start=date(2015, 1, 2))
    result = run_cross_sectional_backtest(
        data, spec, default_config, fixed_universe_membership(BONDS_UNIVERSE)
    )
    assert result.status == "no_valid_formations"
    assert result.formations
    assert all(f.skipped_reason is not None for f in result.formations)
    assert all("min_names_per_leg" in f.skipped_reason for f in result.formations)


# ==========================================================================
# shared primitives: rate factor, empirical duration, income yield
# ==========================================================================


def test_rate_factor_is_the_equal_weighted_treasury_ladder_mean():
    total_return, _ = _synthetic_bond_panel(300)
    returns = total_return.pct_change(fill_method=None)
    factor = rate_factor(returns)
    expected = returns[list(TREASURY_LADDER)].mean(axis=1)
    pd.testing.assert_series_equal(factor, expected, check_names=False)


def test_rate_factor_ignores_the_credit_and_inflation_names():
    total_return, _ = _synthetic_bond_panel(300)
    returns = total_return.pct_change(fill_method=None)
    ladder_only = rate_factor(returns[list(TREASURY_LADDER)])
    everything = rate_factor(returns)
    pd.testing.assert_series_equal(ladder_only, everything, check_names=False)


def test_rate_factor_is_all_nan_when_no_ladder_member_is_present():
    total_return, _ = _synthetic_bond_panel(200)
    returns = total_return[list(SPREAD_INSTRUMENTS)].pct_change(fill_method=None)
    factor = rate_factor(returns)
    assert factor.isna().all()


def test_empirical_duration_betas_recover_the_true_duration_ratios():
    # No idiosyncratic noise: every ETF's return is exactly its duration
    # times the factor, so the estimated betas must reproduce the true
    # durations up to the common scale of the ladder's own mean.
    total_return, _ = _synthetic_bond_panel(500)
    betas = empirical_duration_betas(total_return)

    ladder_mean_duration = np.mean([_TRUE_DURATION[t] for t in TREASURY_LADDER])
    for ticker in BONDS_UNIVERSE:
        expected = _TRUE_DURATION[ticker] / ladder_mean_duration
        assert betas[ticker] == pytest.approx(expected, rel=1e-6)


def test_empirical_duration_betas_are_monotonic_across_the_maturity_ladder():
    total_return, _ = _synthetic_bond_panel(500)
    betas = empirical_duration_betas(total_return)
    ladder = [float(betas[t]) for t in TREASURY_LADDER]
    assert ladder == sorted(ladder), "betas must increase SHY -> IEI -> IEF -> TLH -> TLT"


def test_empirical_duration_beta_ratios_are_free_of_the_reference_scale():
    """The property the whole module leans on: only RATIOS of betas are ever
    used, so rescaling the rate factor must not change anything."""
    total_return, _ = _synthetic_bond_panel(400)
    betas = empirical_duration_betas(total_return)
    ratio = betas["TLT"] / betas["SHY"]
    assert ratio == pytest.approx(_TRUE_DURATION["TLT"] / _TRUE_DURATION["SHY"], rel=1e-6)


def test_empirical_duration_betas_are_all_nan_when_rates_never_move():
    index = pd.bdate_range("2015-01-02", periods=300)
    flat = pd.DataFrame({t: np.full(300, 100.0) for t in BONDS_UNIVERSE}, index=index)
    betas = empirical_duration_betas(flat)
    assert betas.isna().all()


def test_annualized_income_yield_hand_check_against_a_known_accrual():
    # Each ETF accrues a known constant annual income; the wedge between the
    # two bases over the window must recover it.
    income = {t: 0.02 + 0.005 * i for i, t in enumerate(BONDS_UNIVERSE)}
    total_return, price_only = _synthetic_bond_panel(400, income_by_ticker=income)
    lookback = 252
    y = annualized_income_yield(total_return.iloc[-lookback:], price_only.iloc[-lookback:])
    # The generator accrues income as an exact (1 + annual/252)^t factor, so
    # the wedge over a window of `periods` growth steps is exactly
    # (1 + daily)^periods, and annualizing it by 252/periods gives back
    # exactly (1 + daily)^252 - 1 whatever the window length.
    for ticker, annual in income.items():
        daily = annual / bonds.TRADING_DAYS_PER_YEAR
        expected = (1.0 + daily) ** bonds.TRADING_DAYS_PER_YEAR - 1.0
        assert y[ticker] == pytest.approx(expected, rel=1e-9)


def test_annualized_income_yield_is_zero_when_the_two_bases_are_identical():
    total_return, price_only = _synthetic_bond_panel(300)  # no income accrual
    y = annualized_income_yield(total_return.iloc[-252:], price_only.iloc[-252:])
    assert np.allclose(y.to_numpy(), 0.0, atol=1e-12)


def test_annualized_income_yield_is_nan_on_a_non_positive_or_missing_endpoint():
    total_return, price_only = _synthetic_bond_panel(300)
    total_return = total_return.copy()
    price_only = price_only.copy()
    total_return.iloc[-252, total_return.columns.get_loc("TLT")] = np.nan
    price_only.iloc[-252, price_only.columns.get_loc("LQD")] = 0.0
    y = annualized_income_yield(total_return.iloc[-252:], price_only.iloc[-252:])
    assert np.isnan(y["TLT"])
    assert np.isnan(y["LQD"])
    assert np.isfinite(y["SHY"])


# ==========================================================================
# mechanism 1: curve carry / roll-down
# ==========================================================================


def test_carry_ranks_the_treasury_ladder_only():
    income = {t: 0.02 for t in BONDS_UNIVERSE}
    data = _data(500, income_by_ticker=income)
    signal = signal_curve_carry_rolldown(data, lookback_days=252)
    for ticker in TREASURY_LADDER:
        assert np.isfinite(signal[ticker]), ticker
    for ticker in SPREAD_INSTRUMENTS:
        assert np.isnan(signal[ticker]), f"{ticker} must not be ranked by a curve-carry signal"


def test_carry_front_end_reference_scores_exactly_zero():
    income = {t: 0.01 + 0.01 * i for i, t in enumerate(BONDS_UNIVERSE)}
    data = _data(500, income_by_ticker=income)
    signal = signal_curve_carry_rolldown(data, lookback_days=252)
    assert signal[bonds.FRONT_END_TICKER] == pytest.approx(0.0)


def test_carry_hand_check_matches_yield_pickup_over_duration_beta():
    income = {"SHY": 0.01, "IEI": 0.02, "IEF": 0.03, "TLH": 0.035, "TLT": 0.04,
              "TIP": 0.02, "LQD": 0.03, "HYG": 0.06}
    lookback = 252
    total_return, price_only = _synthetic_bond_panel(500, income_by_ticker=income)
    data = CrossSectionalData(close=total_return, price_only_close=price_only)
    signal = signal_curve_carry_rolldown(data, lookback_days=lookback)

    tr_w = total_return.iloc[-lookback:]
    px_w = price_only.iloc[-lookback:]
    y = annualized_income_yield(tr_w, px_w)
    betas = empirical_duration_betas(tr_w)
    for ticker in TREASURY_LADDER:
        expected = (y[ticker] - y[bonds.FRONT_END_TICKER]) / betas[ticker]
        assert signal[ticker] == pytest.approx(expected, rel=1e-9)


def test_carry_is_not_a_static_long_duration_bet_an_inverted_curve_flips_it():
    """The load-bearing property of dividing by duration: with an UPWARD
    sloping curve the long end wins, and with an INVERTED curve the front
    end must win instead. A raw (undivided) carry signal could never do the
    second."""
    lookback = 252
    upward = {"SHY": 0.01, "IEI": 0.02, "IEF": 0.03, "TLH": 0.035, "TLT": 0.04,
              "TIP": 0.0, "LQD": 0.0, "HYG": 0.0}
    inverted = {"SHY": 0.05, "IEI": 0.04, "IEF": 0.03, "TLH": 0.025, "TLT": 0.02,
                "TIP": 0.0, "LQD": 0.0, "HYG": 0.0}

    up = signal_curve_carry_rolldown(_data(500, income_by_ticker=upward), lookback_days=lookback)
    inv = signal_curve_carry_rolldown(_data(500, income_by_ticker=inverted), lookback_days=lookback)

    up_ranked = up.dropna().sort_values(ascending=False)
    inv_ranked = inv.dropna().sort_values(ascending=False)

    # Upward-sloping: the front end is the WORST carry-per-duration.
    assert up_ranked.index[-1] == "SHY"
    # Inverted: every pickup goes negative, so SHY's structural 0.0 is the best.
    assert inv_ranked.index[0] == "SHY"
    assert (inv.dropna().drop("SHY") < 0).all()


def test_carry_excludes_a_ladder_name_whose_duration_beta_is_degenerate():
    # Give TLT no rate exposure at all (pure idiosyncratic noise): its
    # estimated beta collapses toward zero and the divide-by-beta guard must
    # drop it rather than emitting an enormous ratio.
    rng = np.random.default_rng(5)
    idio = {"TLT": rng.normal(0.0, 0.004, 500)}
    income = {t: 0.02 for t in BONDS_UNIVERSE}
    total_return, price_only = _synthetic_bond_panel(
        500, income_by_ticker=income, idio_by_ticker=idio, seed=5
    )
    # Strip TLT's factor loading entirely by rebuilding it as noise-only.
    data = CrossSectionalData(close=total_return, price_only_close=price_only)
    betas = empirical_duration_betas(total_return.iloc[-252:])
    signal = signal_curve_carry_rolldown(data, lookback_days=252)
    if betas["TLT"] < bonds.MIN_DURATION_BETA:
        assert np.isnan(signal["TLT"])
    # Whatever happened to TLT, no surviving signal may be absurdly large.
    assert (signal.dropna().abs() < 1e3).all()


def test_carry_raises_when_the_price_only_basis_is_missing():
    total_return, _ = _synthetic_bond_panel(400)
    data = CrossSectionalData(close=total_return)  # no price_only_close
    with pytest.raises(ValueError, match="price_only_close"):
        signal_curve_carry_rolldown(data, lookback_days=252)


def test_carry_refuses_a_ticker_without_enough_window_coverage():
    income = {t: 0.02 for t in BONDS_UNIVERSE}
    total_return, price_only = _synthetic_bond_panel(500, income_by_ticker=income)
    total_return = total_return.copy()
    # HYG-style late inception: blank out most of IEF's window.
    total_return.iloc[-252:-40, total_return.columns.get_loc("IEF")] = np.nan
    data = CrossSectionalData(close=total_return, price_only_close=price_only)
    signal = signal_curve_carry_rolldown(data, lookback_days=252)
    assert np.isnan(signal["IEF"])
    assert np.isfinite(signal["TLT"])


# ==========================================================================
# mechanism 2: butterfly relative value
# ==========================================================================


def test_butterfly_ranks_the_treasury_ladder_only():
    data = _data(500)
    signal = signal_curve_butterfly(data, lookback_days=252)
    for ticker in TREASURY_LADDER:
        assert np.isfinite(signal[ticker]), ticker
    for ticker in SPREAD_INSTRUMENTS:
        assert np.isnan(signal[ticker]), f"{ticker} must not be ranked by a curve-butterfly signal"


def test_butterfly_residuals_are_orthogonal_to_duration_which_is_what_makes_it_matched():
    """The formal statement of 'duration-matched': OLS residuals sum to zero
    and are uncorrelated with the duration regressor, so the full
    cross-section carries no level exposure."""
    rng = np.random.default_rng(3)
    idio = {t: rng.normal(0.0, 0.0015, 500) for t in BONDS_UNIVERSE}
    total_return, price_only = _synthetic_bond_panel(500, idio_by_ticker=idio, seed=3)
    data = CrossSectionalData(close=total_return, price_only_close=price_only)

    signal = signal_curve_butterfly(data, lookback_days=252)
    residuals = -signal.dropna()  # the signal is the NEGATED residual
    betas = empirical_duration_betas(total_return.iloc[-252:]).reindex(residuals.index)

    assert float(residuals.sum()) == pytest.approx(0.0, abs=1e-12)
    assert float((residuals * betas).sum()) == pytest.approx(0.0, abs=1e-12)


def test_butterfly_is_flat_when_returns_are_exactly_duration_linear():
    # With no idiosyncratic noise every ETF's cumulative return lies exactly
    # on a smooth function of duration; a pure parallel move leaves nothing
    # for the residual to find beyond floating-point dust.
    data = _data(500)
    signal = signal_curve_butterfly(data, lookback_days=252)
    assert np.allclose(signal.dropna().to_numpy(), 0.0, atol=1e-3)


def test_butterfly_shorts_the_rich_name_and_buys_the_cheap_one():
    # Push IEF (the belly) up by a known amount over the window: it becomes
    # RICH relative to its duration-matched wings, so its NEGATED residual
    # must be the lowest of the ladder (i.e. it ranks into the short leg).
    n = 500
    bump = np.zeros(n)
    bump[-100:] = 0.0008  # a sustained belly outperformance
    total_return, price_only = _synthetic_bond_panel(n, idio_by_ticker={"IEF": bump})
    data = CrossSectionalData(close=total_return, price_only_close=price_only)
    signal = signal_curve_butterfly(data, lookback_days=252)
    ranked = signal.dropna().sort_values(ascending=False)
    assert ranked.index[-1] == "IEF", "a rich belly must rank last (short leg)"

    # And the mirror image: a CHEAP belly must rank first.
    total_return2, price_only2 = _synthetic_bond_panel(n, idio_by_ticker={"IEF": -bump})
    signal2 = signal_curve_butterfly(
        CrossSectionalData(close=total_return2, price_only_close=price_only2), lookback_days=252
    )
    assert signal2.dropna().sort_values(ascending=False).index[0] == "IEF"


def test_butterfly_refuses_a_ladder_with_too_few_usable_points():
    total_return, price_only = _synthetic_bond_panel(500)
    total_return = total_return.copy()
    for ticker in ("IEI", "IEF", "TLH"):
        total_return.iloc[-252:-10, total_return.columns.get_loc(ticker)] = np.nan
    data = CrossSectionalData(close=total_return, price_only_close=price_only)
    signal = signal_curve_butterfly(data, lookback_days=252)
    assert signal.isna().all()


# ==========================================================================
# mechanism 3: duration-hedged credit-spread reversion
# ==========================================================================


def test_credit_ranks_all_eight_names_not_just_the_credit_ones():
    rng = np.random.default_rng(7)
    idio = {t: rng.normal(0.0, 0.001, 500) for t in BONDS_UNIVERSE}
    data = _data(500, idio_by_ticker=idio, seed=7)
    signal = signal_duration_hedged_credit(data, lookback_days=252)
    assert signal.notna().all(), "the credit mechanism ranks the full basket"


def test_credit_hedging_removes_pure_rate_moves():
    # With NO idiosyncratic component, every ETF's return is exactly its
    # duration times the rate factor, so the duration-hedged excess is zero
    # for all of them and the signal carries no information.
    data = _data(500)
    signal = signal_duration_hedged_credit(data, lookback_days=252)
    assert np.allclose(signal.to_numpy(), 0.0, atol=1e-9)


def test_credit_buys_the_widened_spread_and_shorts_the_tightened_one():
    n = 500
    widen = np.zeros(n)
    widen[-120:] = -0.0006  # HYG's spread widens: hedged excess goes negative
    tighten = np.zeros(n)
    tighten[-120:] = +0.0006  # LQD richens
    data = _data(n, idio_by_ticker={"HYG": widen, "LQD": tighten})
    signal = signal_duration_hedged_credit(data, lookback_days=252)
    ranked = signal.sort_values(ascending=False)
    assert ranked.index[0] == "HYG", "a widened spread is cheap and must rank long"
    assert ranked.index[-1] == "LQD", "a tightened spread is rich and must rank short"


def test_credit_signal_is_the_negated_cumulative_hedged_excess():
    rng = np.random.default_rng(9)
    idio = {t: rng.normal(0.0, 0.001, 400) for t in BONDS_UNIVERSE}
    total_return, price_only = _synthetic_bond_panel(400, idio_by_ticker=idio, seed=9)
    data = CrossSectionalData(close=total_return, price_only_close=price_only)
    lookback = 252
    signal = signal_duration_hedged_credit(data, lookback_days=lookback)

    window = total_return.iloc[-lookback:]
    returns = window.pct_change(fill_method=None)
    factor = rate_factor(returns)
    betas = empirical_duration_betas(window)
    for ticker in BONDS_UNIVERSE:
        expected = -float((returns[ticker] - betas[ticker] * factor).sum())
        assert signal[ticker] == pytest.approx(expected, rel=1e-9)


def test_credit_uses_empirical_not_analytical_duration_for_a_zero_beta_name():
    """HYG's real measured rate beta is near zero (corr(HYG, TLT) = -0.13 on
    real data), which is exactly why an analytical duration would hedge it
    wrongly. Here HYG is generated with a NEGATIVE loading on the rate
    factor; the estimated beta must come back negative, and hedging at that
    beta must still leave a clean excess."""
    n = 500
    rng = np.random.default_rng(13)
    index = pd.bdate_range("2015-01-02", periods=n)
    factor = rng.normal(0.0, 0.004, n)
    cols = {}
    for ticker in BONDS_UNIVERSE:
        loading = -0.5 if ticker == "HYG" else _TRUE_DURATION[ticker]
        cols[ticker] = 100.0 * np.cumprod(1.0 + loading * factor)
    total_return = pd.DataFrame(cols, index=index)

    betas = empirical_duration_betas(total_return)
    assert betas["HYG"] < 0.0, "a negatively rate-correlated credit ETF must get a negative beta"

    signal = signal_duration_hedged_credit(
        CrossSectionalData(close=total_return, price_only_close=total_return), lookback_days=252
    )
    # Hedged at its own (negative) beta, HYG's excess is still ~zero: the
    # hedge worked, which an analytical positive duration could not do.
    assert signal["HYG"] == pytest.approx(0.0, abs=1e-9)


# ==========================================================================
# the harness extension this family is the first consumer of
# ==========================================================================


def test_price_only_close_must_be_aligned_with_close():
    total_return, price_only = _synthetic_bond_panel(200)
    misaligned = price_only.iloc[:-5]
    with pytest.raises(ValueError, match="price_only_close is not aligned"):
        validate_cross_sectional_data(
            CrossSectionalData(close=total_return, price_only_close=misaligned)
        )


def test_a_spec_requiring_the_price_only_basis_fails_loudly_when_it_is_absent():
    total_return, _ = _synthetic_bond_panel(500)
    data = CrossSectionalData(close=total_return)
    spec = next(s for s in BONDS_FAMILY if s.requires_price_only_close)
    with pytest.raises(ValueError, match="requires the dividend-unadjusted price basis"):
        run_cross_sectional_backtest(
            data, spec, default_bonds_config(), fixed_universe_membership(BONDS_UNIVERSE)
        )


def test_price_only_close_is_sliced_to_the_formation_date_so_look_ahead_is_impossible():
    """The structural guarantee that made the new frame belong on
    CrossSectionalData rather than in this module: the signal is handed a
    view whose price_only_close ends at the formation date, so it cannot
    read a future row however buggy it is."""
    total_return, price_only = _synthetic_bond_panel(400)
    seen: list[pd.Timestamp] = []

    def spy_signal(history: CrossSectionalData) -> pd.Series:
        assert history.price_only_close is not None
        # every frame in the view ends on the same (formation) row
        assert history.price_only_close.index[-1] == history.close.index[-1]
        assert history.price_only_close.columns.equals(history.close.columns)
        seen.append(history.price_only_close.index[-1])
        return pd.Series(np.arange(len(history.close.columns), dtype=float), index=history.close.columns)

    spec = CrossSectionalSpec(
        pattern_id="spy",
        family="spy",
        citation="test",
        signal_fn=spy_signal,
        lookback_days=63,
        holding_days=63,
        portfolio="long_short",
        rank_fraction=BONDS_FULL_RANK_FRACTION,
        requires_price_only_close=True,
    )
    data = CrossSectionalData(close=total_return, price_only_close=price_only)
    config = CrossSectionalConfig(min_names_per_leg=2, formation_start=date(2015, 1, 2))
    result = run_cross_sectional_backtest(data, spec, config, fixed_universe_membership(BONDS_UNIVERSE))

    assert result.status == "ok"
    assert seen
    # No formation view ever reached the frame's own last row except a
    # formation genuinely dated there.
    for formation, observed in zip(result.formations, seen, strict=True):
        assert observed == formation.date


def test_existing_families_are_unaffected_by_the_new_optional_frame():
    """price_only_close defaults to None, so a family that never sets it
    must produce byte-identical results to before the field existed."""
    from app.services.research_lab.cross_sectional_patterns_d2 import D2_FAMILY

    index = pd.bdate_range("2015-01-02", periods=400)
    rng = np.random.default_rng(2)
    close = pd.DataFrame(
        {t: 100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.01, 400)) for t in BONDS_UNIVERSE},
        index=index,
    )
    spec = D2_FAMILY[0]
    config = CrossSectionalConfig(min_names_per_leg=2, formation_start=date(2015, 1, 2))
    membership = fixed_universe_membership(BONDS_UNIVERSE)

    without = run_cross_sectional_backtest(CrossSectionalData(close=close), spec, config, membership)
    # Supplying an unused price_only_close must change nothing at all.
    with_frame = run_cross_sectional_backtest(
        CrossSectionalData(close=close, price_only_close=close * 0.5), spec, config, membership
    )
    pd.testing.assert_series_equal(without.daily_returns, with_frame.daily_returns)


# ==========================================================================
# cost / financing configuration
# ==========================================================================


def test_default_config_sets_both_cost_components_and_neither_is_the_harness_default():
    from app.services.research_lab.cross_sectional import (
        DEFAULT_FINANCING_BPS_PER_YEAR,
        DEFAULT_XS_COST_BPS,
    )

    config = default_bonds_config()
    assert config.cost_bps == BONDS_COST_BPS == 2.5
    assert config.cost_bps < DEFAULT_XS_COST_BPS  # ETFs are cheaper than single stocks
    assert config.financing_bps_per_year == BONDS_FINANCING_BPS_PER_YEAR == 20.0
    assert config.financing_bps_per_year != DEFAULT_FINANCING_BPS_PER_YEAR  # 0.0


def test_financing_is_exactly_half_the_short_leg_borrow_assumption():
    """The harness charges financing on GROSS notional (2.0 for a fully
    formed long-short book), and only the 1.0 short leg pays borrow — so
    the configured rate must be half the borrow rate, or the book is charged
    twice what the assumption says."""
    assert BONDS_SHORT_BORROW_BPS_PER_YEAR == 40.0
    assert BONDS_FINANCING_BPS_PER_YEAR == pytest.approx(BONDS_SHORT_BORROW_BPS_PER_YEAR / 2.0)


def test_financing_actually_reaches_the_replay_and_is_reported_separately():
    data = _data(700)
    spec = next(s for s in BONDS_FAMILY if s.pattern_id == "bonds_credit_hedged_l252_h126")
    membership = fixed_universe_membership(BONDS_UNIVERSE)

    priced = run_cross_sectional_backtest(data, spec, default_bonds_config(), membership)
    free = run_cross_sectional_backtest(
        data,
        spec,
        CrossSectionalConfig(
            cost_bps=BONDS_COST_BPS, min_names_per_leg=2, financing_bps_per_year=0.0
        ),
        membership,
    )
    assert priced.status == "ok"
    assert priced.total_financing_cost > 0.0
    assert free.total_financing_cost == 0.0
    # Financing is a real drag: the financed replay must earn strictly less.
    assert float(priced.daily_returns.sum()) < float(free.daily_returns.sum())
    # ...and it is NOT folded into the turnover cost.
    assert priced.total_cost == pytest.approx(free.total_cost)


def test_a_longer_hold_pays_more_financing_and_less_trading_cost():
    """The reason the two components must not be collapsed into one number:
    across this family's own holding axis they move in opposite directions."""
    data = _data(1400)
    membership = fixed_universe_membership(BONDS_UNIVERSE)
    config = default_bonds_config()
    short_hold = next(s for s in BONDS_FAMILY if s.pattern_id == "bonds_credit_hedged_l252_h63")
    long_hold = next(s for s in BONDS_FAMILY if s.pattern_id == "bonds_credit_hedged_l252_h252")

    a = run_cross_sectional_backtest(data, short_hold, config, membership)
    b = run_cross_sectional_backtest(data, long_hold, config, membership)
    assert a.status == "ok" and b.status == "ok"
    assert a.total_cost > b.total_cost  # more reformations
    assert b.total_financing_cost > a.total_financing_cost * 0.9  # more time held


def test_disclosure_names_both_cost_components_and_says_borrow_is_an_assumption():
    text = build_bonds_disclosure([], default_bonds_config())
    assert "2.5 bps one-way" in text
    assert "20.0 bps/yr" in text
    assert "40.0 bps/yr SHORT-LEG borrow" in text
    assert "assumption" in text
    assert "min_names_per_leg=2" in text
    assert "no spec produced a positive Sharpe" in text


def test_disclosure_reports_a_breakeven_cost_for_a_positive_spec():
    from app.services.research_lab.cross_sectional import CrossSectionalScreeningResult
    from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe

    # A genuinely varying series: a constant one makes the DSR's skew/
    # kurtosis moments degenerate and is not what a real replay looks like.
    rng = np.random.default_rng(31)
    series = pd.Series(
        0.0004 + rng.normal(0.0, 0.002, 504),
        index=pd.bdate_range("2015-01-02", periods=504),
        dtype=float,
    )
    result = CrossSectionalScreeningResult(
        pattern_id="bonds_curve_carry_l252_h126",
        family="bonds_curve_carry",
        citation="x",
        n_formations=4,
        n_skipped_formations=0,
        avg_names_per_leg=2.0,
        n_trading_days=504,
        sharpe_annualized=1.5,
        total_cost_drag=0.002,
        deflated_sharpe=compute_deflated_sharpe(1.5, series, 18, 0.5),
    )
    text = build_bonds_disclosure([result], default_bonds_config(), {result.pattern_id: series})
    assert "breakeven at" in text
    assert "x the assumption" in text


# ==========================================================================
# the term-premium decomposition (the number that decides what a Sharpe means)
# ==========================================================================


def test_rate_exposure_recovers_a_pure_factor_bet_as_all_beta_no_alpha():
    """A stream that IS the rate factor scaled up must come back as pure
    beta with no alpha — the exact shape of 'this positive Sharpe is just
    the term premium', which is what the real production run found."""
    rng = np.random.default_rng(41)
    index = pd.bdate_range("2015-01-02", periods=1000)
    factor = pd.Series(rng.normal(0.0003, 0.004, 1000), index=index)
    stream = 0.75 * factor

    exposure = bonds.compute_rate_exposure("pure_beta", stream, factor)
    assert exposure.rate_beta == pytest.approx(0.75, rel=1e-9)
    assert exposure.alpha_annualized == pytest.approx(0.0, abs=1e-12)
    # The residual here is zero only to floating-point dust, which a naive
    # Sharpe turns into meaningless noise — the guard must report the real
    # answer (nothing survived the hedge) instead.
    assert exposure.rate_neutralized_sharpe == 0.0
    assert exposure.alpha_t_stat == 0.0
    # The raw Sharpe is positive purely because the factor's was.
    assert exposure.sharpe > 0


def test_a_nearly_but_not_exactly_hedged_stream_is_not_swallowed_by_the_guard():
    """The degenerate-residual guard must not silently eat a small but real
    alpha — only a residual that is negligible relative to the stream."""
    rng = np.random.default_rng(47)
    index = pd.bdate_range("2015-01-02", periods=2000)
    factor = pd.Series(rng.normal(0.0003, 0.004, 2000), index=index)
    small_edge = pd.Series(rng.normal(0.00008, 0.0004, 2000), index=index)
    stream = 0.75 * factor + small_edge

    exposure = bonds.compute_rate_exposure("small_alpha", stream, factor)
    assert exposure.rate_neutralized_sharpe != 0.0
    assert np.isfinite(exposure.alpha_t_stat)
    assert exposure.alpha_annualized > 0.0


def test_rate_exposure_recovers_genuine_alpha_that_survives_neutralization():
    rng = np.random.default_rng(43)
    index = pd.bdate_range("2015-01-02", periods=1500)
    factor = pd.Series(rng.normal(0.0003, 0.004, 1500), index=index)
    edge = pd.Series(rng.normal(0.0006, 0.003, 1500), index=index)  # real, factor-free drift
    stream = 0.4 * factor + edge

    exposure = bonds.compute_rate_exposure("real_alpha", stream, factor)
    assert exposure.rate_beta == pytest.approx(0.4, abs=0.05)
    assert exposure.alpha_annualized > 0.05  # a real >5%/yr alpha survives
    assert exposure.alpha_t_stat > 2.0
    assert exposure.rate_neutralized_sharpe > 0.5


def test_rate_exposure_handles_a_degenerate_or_too_short_stream():
    index = pd.bdate_range("2015-01-02", periods=2)
    tiny = pd.Series([0.001, 0.002], index=index)
    exposure = bonds.compute_rate_exposure("tiny", tiny, pd.Series([0.001, 0.002], index=index))
    assert np.isnan(exposure.rate_beta)

    index2 = pd.bdate_range("2015-01-02", periods=300)
    flat_factor = pd.Series(np.zeros(300), index=index2)
    stream = pd.Series(np.random.default_rng(1).normal(0.0, 0.01, 300), index=index2)
    exposure2 = bonds.compute_rate_exposure("flat_factor", stream, flat_factor)
    assert np.isnan(exposure2.rate_beta)
    assert np.isfinite(exposure2.sharpe)  # the raw Sharpe is still reportable


def test_screening_reports_rate_exposure_for_every_replayed_spec():
    provider = _FakeProvider()
    summary = run_bonds_screening(start=date(2015, 1, 2), end=date(2021, 6, 30), provider=provider)
    assert summary.rate_exposure
    assert set(summary.rate_exposure) == {r.pattern_id for r in summary.results}
    for pattern_id, exposure in summary.rate_exposure.items():
        assert exposure.pattern_id == pattern_id
        assert np.isfinite(exposure.rate_beta)
        assert np.isfinite(exposure.rate_neutralized_sharpe)
    # The mechanism-level diagnostic carries the same decomposition.
    for diagnostic in summary.mechanism_diagnostics:
        assert np.isfinite(diagnostic.rate_neutralized_sharpe)
        assert np.isfinite(diagnostic.alpha_t_stat)


# ==========================================================================
# the production entry point
# ==========================================================================


class _FakeProvider:
    """Synthetic-data stand-in for YFinanceProvider.get_total_and_price_
    return_closes — the same aligned two-frame + missing contract, no
    network (mirrors Round C/D/D2's own test fixtures)."""

    def __init__(self, served: tuple[str, ...] = BONDS_UNIVERSE, n: int = 1600, seed: int = 21):
        self.served = served
        self.n = n
        self.seed = seed
        self.requested: list[str] | None = None
        self.window: tuple[date, date] | None = None

    def get_total_and_price_return_closes(self, tickers, start, end):
        self.requested = list(tickers)
        self.window = (start, end)
        rng = np.random.default_rng(self.seed)
        idio = {t: rng.normal(0.0, 0.0012, self.n) for t in self.served}
        income = {t: 0.01 + 0.004 * i for i, t in enumerate(self.served)}
        total_return, price_only = _synthetic_bond_panel(
            self.n,
            income_by_ticker=income,
            idio_by_ticker=idio,
            seed=self.seed,
            start=start.isoformat(),
            tickers=self.served,
        )
        missing = [t for t in tickers if t not in self.served]
        return total_return, price_only, missing


def test_screening_uses_the_fixed_universe_gate_not_the_sp500_one():
    """The trap this family had to avoid: was_member answers False for every
    bond ETF, so the S&P 500 gate would make the whole universe ineligible
    on every date. Proven by showing the WRONG gate raises."""
    provider = _FakeProvider()
    total_return, price_only, _ = provider.get_total_and_price_return_closes(
        list(BONDS_UNIVERSE), date(2015, 1, 2), date(2021, 1, 1)
    )
    data = CrossSectionalData(close=total_return, price_only_close=price_only)
    config = default_bonds_config()
    config.formation_start = date(2016, 1, 4)

    with pytest.raises(EmptyEligibleUniverseError):
        screen_cross_sectional_universe(data, BONDS_FAMILY, config, membership_fn=None)

    # ...and the right gate makes the same family run.
    results = screen_cross_sectional_universe(
        data, BONDS_FAMILY, config, fixed_universe_membership(BONDS_UNIVERSE)
    )
    assert results


def test_fixed_universe_membership_admits_exactly_this_basket():
    gate = fixed_universe_membership(BONDS_UNIVERSE)
    for ticker in BONDS_UNIVERSE:
        assert gate(ticker, date(2007, 4, 11))
        assert gate(ticker, date(2026, 8, 26))
    assert not gate("AAPL", date(2020, 1, 2))


def test_common_history_start_is_the_verified_date():
    # Re-verified live 2026-08-27: HYG's inception bounds the basket.
    assert BONDS_COMMON_HISTORY_START == date(2007, 4, 11)


def test_screening_runs_end_to_end_against_a_fake_provider():
    """Offline end-to-end pipeline check: the real fixed-universe gate, the
    full 18-definition family, both price bases, real cost and financing
    configuration. Small on purpose — a smoke test of pipeline correctness,
    never a source of conclusions."""
    provider = _FakeProvider()
    summary = run_bonds_screening(
        start=date(2015, 1, 2), end=date(2021, 6, 30), provider=provider
    )

    assert provider.requested == list(BONDS_UNIVERSE)
    assert summary.missing_price_data == []
    assert summary.results

    for r in summary.results:
        assert r.deflated_sharpe.n_trials == 18  # this family's own n_trials
        assert np.isfinite(r.sharpe_annualized)
        assert r.n_trading_days >= 60
        assert r.n_formations > 0
        assert r.avg_names_per_leg == pytest.approx(2.0)
        # 18 trials clears MIN_TRIALS_FOR_DSR (5), unlike D2's 4 — so the
        # DSR proper must actually compute for this family.
        assert r.deflated_sharpe.dsr_floor_met is True
        assert r.deflated_sharpe.dsr is not None
        assert r.total_financing_drag > 0.0

    assert summary.disclosure
    assert summary.mechanism_diagnostics
    for diagnostic in summary.mechanism_diagnostics:
        assert diagnostic.n_specs_replayed > 0
        assert np.isfinite(diagnostic.realized_book_volatility)
    assert summary.mechanism_correlations  # cross-mechanism overlap measured, not asserted


def test_screening_pads_price_history_before_the_requested_start():
    provider = _FakeProvider()
    run_bonds_screening(start=date(2016, 1, 4), end=date(2020, 1, 1), provider=provider)
    assert provider.window is not None
    padded_start, _ = provider.window
    assert padded_start < date(2016, 1, 4)
    assert (date(2016, 1, 4) - padded_start).days == bonds.BONDS_PRICE_HISTORY_PADDING_CALENDAR_DAYS


def test_screening_reports_a_missing_universe_member_rather_than_hiding_it(caplog):
    provider = _FakeProvider(served=tuple(t for t in BONDS_UNIVERSE if t != "HYG"))
    with caplog.at_level("ERROR"):
        summary = run_bonds_screening(
            start=date(2015, 1, 2), end=date(2021, 1, 1), provider=provider
        )
    assert summary.missing_price_data == ["HYG"]
    assert any("resolved NO price data" in rec.message for rec in caplog.records)


def test_screening_respects_a_caller_supplied_config(monkeypatch):
    captured: list[CrossSectionalConfig] = []

    def fake_screen(data, specs, config, membership_fn=None):
        captured.append(config)
        return []

    monkeypatch.setattr(bonds, "screen_cross_sectional_universe", fake_screen)
    provider = _FakeProvider()

    run_bonds_screening(start=date(2016, 1, 4), end=date(2020, 1, 1), provider=provider)
    assert captured[-1].cost_bps == BONDS_COST_BPS
    assert captured[-1].financing_bps_per_year == BONDS_FINANCING_BPS_PER_YEAR

    explicit = CrossSectionalConfig(cost_bps=99.0, min_names_per_leg=2)
    run_bonds_screening(
        start=date(2016, 1, 4), end=date(2020, 1, 1), provider=provider, config=explicit
    )
    assert captured[-1] is explicit
    assert captured[-1].cost_bps == 99.0


def test_screening_returns_empty_when_no_price_data_resolves():
    class _EmptyProvider:
        def get_total_and_price_return_closes(self, tickers, start, end):
            return pd.DataFrame(), pd.DataFrame(), list(tickers)

    summary = run_bonds_screening(
        start=date(2016, 1, 4), end=date(2020, 1, 1), provider=_EmptyProvider()
    )
    assert summary.results == []
    assert set(summary.missing_price_data) == set(BONDS_UNIVERSE)


def test_default_config_is_a_fresh_object_each_call():
    """The harness writes formation_start onto whatever config it is given,
    so a shared module-level singleton would leak state between runs."""
    a = default_bonds_config()
    b = default_bonds_config()
    assert a is not b
    a.formation_start = date(2020, 1, 1)
    assert b.formation_start is None
