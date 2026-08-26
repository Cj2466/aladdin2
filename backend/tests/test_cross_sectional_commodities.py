from datetime import date

import numpy as np
import pandas as pd
import pytest

import app.services.research_lab.cross_sectional_commodities as cmod
from app.services.research_lab.cross_sectional import (
    CrossSectionalData,
)
from app.services.research_lab.cross_sectional_commodities import (
    COMMODITIES_COST_BPS,
    COMMODITIES_EXCLUDED_REDUNDANT,
    COMMODITIES_FINANCING_BPS_PER_YEAR,
    COMMODITIES_LOOKBACK_DAYS,
    COMMODITIES_MIN_NAMES_PER_LEG,
    COMMODITIES_N_TRIALS,
    COMMODITIES_RANK_FRACTION,
    COMMODITIES_REDUNDANCY_CORR_LIMIT,
    COMMODITIES_SHORT_BORROW_BPS_PER_YEAR,
    COMMODITIES_UNIVERSE,
    COMMODITY_HOLDING_DAYS,
    COMMODITY_LEG_WEIGHTINGS,
    COMMODITY_MOMENTUM_LOOKBACK_DAYS,
    COMMODITY_REVERSAL_LOOKBACK_DAYS,
    COMMODITY_SPIKE_MIN_ABS_RETURN,
    COMMODITY_SPIKE_REVERSAL_FRACTION,
    build_commodities_family,
    build_commodities_price_panel,
    build_inverse_vol_basis,
    default_commodities_config,
    effective_breadth,
    run_commodities_screening,
    scrub_commodity_bad_prints,
    signal_commodity_long_run_reversal,
    signal_commodity_momentum,
    signal_commodity_momentum_value_blend,
)


def _frame(values_by_ticker: dict[str, list[float]], start: str = "2012-01-03") -> pd.DataFrame:
    n = len(next(iter(values_by_ticker.values())))
    return pd.DataFrame(values_by_ticker, index=pd.bdate_range(start, periods=n))


def _history(close: pd.DataFrame) -> CrossSectionalData:
    return CrossSectionalData(close=close)


# --- family shape: exactly 24, no more, no fewer ---------------------------


def test_family_is_exactly_24_definitions_and_matches_the_declared_arithmetic():
    family = build_commodities_family()
    assert len(family) == 24
    assert COMMODITIES_N_TRIALS == 24
    # 6 signal definitions x 2 holds x 2 weightings — the count is DERIVED
    # from the axes, never a typed literal that could drift from them.
    n_signals = len(COMMODITY_MOMENTUM_LOOKBACK_DAYS) + len(COMMODITY_REVERSAL_LOOKBACK_DAYS) + 1
    assert n_signals == 6
    assert COMMODITIES_N_TRIALS == n_signals * len(COMMODITY_HOLDING_DAYS) * len(
        COMMODITY_LEG_WEIGHTINGS
    )


def test_family_covers_every_axis_combination_exactly_once():
    family = build_commodities_family()
    assert {s.holding_days for s in family} == set(COMMODITY_HOLDING_DAYS) == {63, 126}
    assert {s.leg_weighting for s in family} == set(COMMODITY_LEG_WEIGHTINGS) == {
        "equal",
        "inverse_vol",
    }
    assert len({s.pattern_id for s in family}) == len(family)
    stems = [s.pattern_id.rsplit("_h", 1)[0] for s in family]
    assert len(set(stems)) == 6
    assert all(
        stems.count(stem) == len(COMMODITY_HOLDING_DAYS) * len(COMMODITY_LEG_WEIGHTINGS)
        for stem in set(stems)
    )


def test_family_declares_no_21_day_hold():
    # At H=21 the turnover charge triples while the time-based financing
    # charge stands — this family's own cost arithmetic, on top of the
    # project-wide record that shorter holds lost in every family to date.
    assert 21 not in COMMODITY_HOLDING_DAYS
    assert all(s.holding_days >= 63 for s in build_commodities_family())


def test_family_is_close_only():
    for spec in build_commodities_family():
        assert not spec.requires_open
        assert not spec.requires_volume
        assert not spec.requires_market_cap
        assert not spec.requires_price_only_close


def test_family_every_spec_is_cited_and_shares_the_common_parameters():
    for spec in build_commodities_family():
        assert spec.citation
        assert spec.portfolio == "long_short"
        # The family-max lookback shared by all 24 so sibling Sharpes are
        # measured on one sample (the sigma_sr argument the FX family
        # documents).
        assert spec.lookback_days == COMMODITIES_LOOKBACK_DAYS == 1260
        assert spec.rank_fraction == pytest.approx(1.0 / 3.0)
        assert spec.cohort_formation_days is None


def test_family_pattern_ids_do_not_collide_with_any_other_family():
    from app.services.research_lab.cross_sectional_bonds import BONDS_FAMILY
    from app.services.research_lab.cross_sectional_fx import (
        FX_CURRENCIES,
        build_fx_family,
    )
    from app.services.research_lab.cross_sectional_ivol import ROUND_D1_FAMILY
    from app.services.research_lab.cross_sectional_patterns import ROUND_C_FAMILY
    from app.services.research_lab.cross_sectional_patterns_d2 import D2_FAMILY
    from app.services.research_lab.cross_sectional_patterns_round_d import (
        ROUND_D_LPS_INTRADAY_FAMILY,
    )

    cmd_ids = {s.pattern_id for s in build_commodities_family()}
    fx_family = build_fx_family(pd.DataFrame(columns=FX_CURRENCIES))
    other = (
        {s.pattern_id for s in ROUND_C_FAMILY}
        | {s.pattern_id for s in D2_FAMILY}
        | {s.pattern_id for s in ROUND_D_LPS_INTRADAY_FAMILY}
        | {s.pattern_id for s in ROUND_D1_FAMILY}
        | {s.pattern_id for s in BONDS_FAMILY}
        | {s.pattern_id for s in fx_family}
    )
    assert cmd_ids.isdisjoint(other)


def test_tercile_legs_are_three_tickers_and_disjoint():
    n_leg = max(1, int(len(COMMODITIES_UNIVERSE) * COMMODITIES_RANK_FRACTION))
    assert n_leg == 3
    assert 2 * n_leg <= len(COMMODITIES_UNIVERSE)
    assert COMMODITIES_MIN_NAMES_PER_LEG == 3


def test_universe_is_one_instrument_per_commodity_and_excludes_redundant():
    assert len(COMMODITIES_UNIVERSE) == 11
    assert len(set(COMMODITIES_UNIVERSE)) == 11
    # The pre-declared redundancy rule: BNO measured 0.942 against USO —
    # over the 0.90 limit — so exactly one crude proxy is in the basket.
    kept, corr = COMMODITIES_EXCLUDED_REDUNDANT["BNO"]
    assert kept == "USO" and kept in COMMODITIES_UNIVERSE
    assert corr > COMMODITIES_REDUNDANCY_CORR_LIMIT
    assert "BNO" not in COMMODITIES_UNIVERSE
    # One instrument per commodity: no duplicate wrappers, no baskets.
    assert {"IAU", "SGOL", "DBC", "DBA", "DBB", "DBE", "GSG"}.isdisjoint(COMMODITIES_UNIVERSE)


# --- the bad-print scrub at commodity calibration --------------------------


def test_scrub_removes_a_25_percent_spike_that_round_trips():
    # The CPER 2014-12-04 shape: -33% printed, +50% the next day, two-day
    # net ~+0.2% (copper futures moved +1.4% that day — a proven bad print).
    prices = [100.0] * 10 + [66.85] + [100.2] + [100.0] * 10
    frame = _frame({"CPER": prices, "GLD": [100.0 + 0.1 * i for i in range(len(prices))]})
    scrubbed, flags = scrub_commodity_bad_prints(frame)
    assert int(flags["CPER"].sum()) == 1
    assert np.isnan(scrubbed["CPER"].iloc[10])
    assert int(flags["GLD"].sum()) == 0


def test_scrub_preserves_a_real_crash_that_does_not_reverse():
    # The USO 2020-03-09 shape: -25.3% followed by only a partial bounce —
    # the two-day move keeps ~76% of the crash. A real repricing, kept.
    prices = [100.0] * 10 + [74.7] + [80.7] + [80.0] * 10
    frame = _frame({"USO": prices})
    scrubbed, flags = scrub_commodity_bad_prints(frame)
    assert int(flags["USO"].sum()) == 0
    assert not scrubbed["USO"].isna().any()


def test_scrub_spares_commodity_scale_whipsaws_below_the_magnitude_floor():
    # The UNG 2018-11-14 shape: +18.9% then -19.1%, a genuine natural-gas
    # squeeze that fully round-trips. FX's 4% threshold would delete it;
    # the commodity calibration must not — |move| < 25%.
    prices = [100.0] * 10 + [118.9] + [96.2] + [96.0] * 10
    frame = _frame({"UNG": prices})
    scrubbed, flags = scrub_commodity_bad_prints(frame)
    assert int(flags["UNG"].sum()) == 0
    assert not scrubbed["UNG"].isna().any()


def test_scrub_calibration_is_the_declared_one():
    assert COMMODITY_SPIKE_MIN_ABS_RETURN == 0.25
    assert COMMODITY_SPIKE_REVERSAL_FRACTION == 0.20


# --- signals ----------------------------------------------------------------


def test_momentum_ranks_the_winner_above_the_loser_and_hand_checks():
    n = 130
    close = _frame(
        {
            "GLD": list(np.linspace(100.0, 150.0, n)),  # +50%
            "USO": list(np.linspace(100.0, 80.0, n)),  # -20%
            "CORN": [100.0] * n,  # flat
        }
    )
    signal = signal_commodity_momentum(_history(close), lookback_days=126)
    assert signal["GLD"] > signal["CORN"] > signal["USO"]
    window = close.iloc[-126:]
    assert signal["GLD"] == pytest.approx(window["GLD"].iloc[-1] / window["GLD"].iloc[0] - 1.0)


def test_momentum_is_nan_when_the_window_is_underpopulated():
    n = 130
    values = [np.nan] * 60 + list(np.linspace(100.0, 120.0, n - 60))
    close = _frame({"GLD": values, "USO": list(np.linspace(100.0, 90.0, n))})
    signal = signal_commodity_momentum(_history(close), lookback_days=126)
    # GLD has only 70 of the required 0.8 * 126 ≈ 100 observations.
    assert np.isnan(signal["GLD"])
    assert np.isfinite(signal["USO"])


def test_reversal_is_exactly_the_negated_momentum():
    n = 800
    rng = np.random.default_rng(11)
    close = _frame(
        {
            "GLD": list(100.0 * np.cumprod(1 + rng.normal(0.0002, 0.01, n))),
            "USO": list(100.0 * np.cumprod(1 + rng.normal(-0.0002, 0.02, n))),
        }
    )
    history = _history(close)
    momentum = signal_commodity_momentum(history, lookback_days=756)
    reversal = signal_commodity_long_run_reversal(history, lookback_days=756)
    pd.testing.assert_series_equal(reversal, -momentum)


def test_blend_is_a_rank_average_and_nan_when_either_component_is_missing():
    n = 1300
    rng = np.random.default_rng(5)
    cols = {
        t: list(100.0 * np.cumprod(1 + rng.normal(mu, 0.01, n)))
        for t, mu in [("GLD", 0.0004), ("USO", -0.0004), ("CORN", 0.0001), ("SLV", 0.0)]
    }
    # SLV is missing most of the momentum window -> NaN momentum -> NaN blend.
    cols["SLV"] = [np.nan] * (n - 40) + cols["SLV"][n - 40 :]
    close = _frame(cols)
    history = _history(close)
    blend = signal_commodity_momentum_value_blend(
        history, momentum_lookback_days=126, reversal_lookback_days=1260
    )
    momentum = signal_commodity_momentum(history, lookback_days=126)
    reversal = signal_commodity_long_run_reversal(history, lookback_days=1260)
    assert np.isnan(blend["SLV"])
    finite = [t for t in ("GLD", "USO", "CORN") if np.isfinite(blend[t])]
    assert finite == ["GLD", "USO", "CORN"]
    # Hand-check one value: mean of the two [0,1] ranks.
    m_rank = momentum[finite].rank() / len(finite)
    r_rank = reversal[finite].rank() / len(finite)
    for t in finite:
        assert blend[t] == pytest.approx((m_rank[t] + r_rank[t]) / 2.0)


# --- inverse-vol basis ------------------------------------------------------


def test_inverse_vol_basis_is_larger_for_the_calmer_ticker():
    n = 260
    rng = np.random.default_rng(3)
    close = _frame(
        {
            "GLD": list(100.0 * np.cumprod(1 + rng.normal(0, 0.005, n))),
            "UNG": list(100.0 * np.cumprod(1 + rng.normal(0, 0.03, n))),
        }
    )
    basis = build_inverse_vol_basis(close)
    assert basis["GLD"].iloc[-1] > basis["UNG"].iloc[-1]


def test_inverse_vol_basis_is_point_in_time_and_never_infinite():
    n = 200
    close = _frame({"GLD": [100.0] * n, "UNG": list(np.linspace(100, 120, n))})
    basis = build_inverse_vol_basis(close)
    # A constant price has zero vol: NaN, never inf.
    assert not np.isinf(basis.to_numpy()).any()
    assert basis["GLD"].dropna().empty
    # Point-in-time: the basis at row i must not change when later rows do.
    perturbed = close.copy()
    perturbed.iloc[-1, perturbed.columns.get_loc("UNG")] *= 2.0
    basis2 = build_inverse_vol_basis(perturbed)
    pd.testing.assert_series_equal(basis["UNG"].iloc[:-1], basis2["UNG"].iloc[:-1])


# --- effective breadth ------------------------------------------------------


def test_effective_breadth_counts_independent_bets_not_tickers():
    n = 500
    rng = np.random.default_rng(9)
    a = rng.normal(0, 0.01, n)
    b = rng.normal(0, 0.01, n)
    c = rng.normal(0, 0.01, n)
    index = pd.bdate_range("2015-01-01", periods=n)
    independent = pd.DataFrame({"A": a, "B": b, "C": c}, index=index)
    duplicated = pd.DataFrame({"A": a, "A2": a, "C": c}, index=index)
    n_ind = effective_breadth(independent)
    n_dup = effective_breadth(duplicated)
    assert n_ind == pytest.approx(3.0, abs=0.2)
    # Three columns, one an exact copy: eigenvalues ~(2,1,0) -> 9/5 = 1.8.
    assert n_dup == pytest.approx(1.8, abs=0.2)
    assert n_dup < n_ind


def test_effective_breadth_is_nan_when_degenerate():
    index = pd.bdate_range("2015-01-01", periods=10)
    assert np.isnan(effective_breadth(pd.DataFrame({"A": np.zeros(10)}, index=index)))
    assert np.isnan(effective_breadth(pd.DataFrame(index=index)))


# --- config -----------------------------------------------------------------


def test_default_config_sets_both_costs_and_the_leg_floor_and_is_fresh_each_call():
    config = default_commodities_config()
    assert config.cost_bps == COMMODITIES_COST_BPS == 5.0
    assert (
        config.financing_bps_per_year
        == COMMODITIES_FINANCING_BPS_PER_YEAR
        == COMMODITIES_SHORT_BORROW_BPS_PER_YEAR / 2.0
    )
    assert config.min_names_per_leg == COMMODITIES_MIN_NAMES_PER_LEG == 3
    # Fresh object per call: the harness writes formation_start onto its
    # config, and a shared singleton would leak that between runs.
    config.formation_start = date(2020, 1, 1)
    assert default_commodities_config().formation_start is None


# --- panel construction -----------------------------------------------------


class _SyntheticProvider:
    """Deterministic random-walk closes for the full universe, with one
    CPER-style fabricated print injected so the panel-level scrub has real
    work to do. get_daily_ohlcv-shaped, like the harness's real provider."""

    def __init__(self, n: int = 2200, seed: int = 7, inject_bad_print: bool = True):
        rng = np.random.default_rng(seed)
        index = pd.bdate_range("2016-01-04", periods=n)
        drifts = np.linspace(-0.0004, 0.0006, len(COMMODITIES_UNIVERSE))
        vols = np.linspace(0.006, 0.02, len(COMMODITIES_UNIVERSE))
        columns = {
            t: 100.0 * np.cumprod(1 + rng.normal(mu, sd, n))
            for t, mu, sd in zip(COMMODITIES_UNIVERSE, drifts, vols, strict=True)
        }
        close = pd.DataFrame(columns, index=index)
        if inject_bad_print:
            # A -35% print that fully reverses the next row.
            spike = min(400, n - 10)
            row = close.columns.get_loc("CPER")
            close.iloc[spike, row] = close.iloc[spike - 1, row] * 0.65
        self.close = close

    def get_daily_ohlcv(self, tickers, start, end):
        mask = (self.close.index.date >= start) & (self.close.index.date <= end)
        subset = self.close.loc[mask, [t for t in tickers if t in self.close.columns]]
        missing = [t for t in tickers if t not in self.close.columns]
        return {"close": subset}, missing


def test_panel_scrubs_the_injected_bad_print_and_keeps_the_rest():
    provider = _SyntheticProvider(n=600)
    panel, flags, missing = build_commodities_price_panel(provider, end=date(2018, 12, 31))
    assert missing == []
    assert list(panel.columns) == list(COMMODITIES_UNIVERSE)
    assert int(flags.to_numpy().sum()) == 1
    assert int(flags["CPER"].sum()) == 1
    assert panel["CPER"].isna().sum() == 1


def test_panel_is_empty_when_the_provider_returns_nothing():
    class _EmptyProvider:
        def get_daily_ohlcv(self, tickers, start, end):
            return {}, list(tickers)

    panel, _flags, missing = build_commodities_price_panel(_EmptyProvider(), end=date(2020, 1, 1))
    assert panel.empty
    assert set(missing) == set(COMMODITIES_UNIVERSE)


# --- entry point ------------------------------------------------------------


def test_screening_uses_fixed_universe_membership_not_the_equity_gate(monkeypatch):
    captured: list = []

    def fake_screen(data, specs, config, membership_fn=None):
        captured.append(membership_fn)
        return []

    monkeypatch.setattr(cmod, "screen_cross_sectional_universe", fake_screen)
    run_commodities_screening(end=date(2018, 12, 31), provider=_SyntheticProvider(n=300))
    membership_fn = captured[-1]
    assert membership_fn is not None, "membership_fn=None would route commodities to the S&P gate"
    for ticker in COMMODITIES_UNIVERSE:
        assert membership_fn(ticker, date(2018, 6, 1)) is True
    assert membership_fn("AAPL", date(2018, 6, 1)) is False
    assert membership_fn("BNO", date(2018, 6, 1)) is False


def test_screening_runs_end_to_end_offline_and_reports_every_disclosure():
    """Offline end-to-end smoke test: the real family, the real harness, the
    real membership gate, synthetic prices carrying an injected bad print.
    Small on purpose — a pipeline check, never a source of conclusions."""
    summary = run_commodities_screening(
        end=date(2024, 12, 31), provider=_SyntheticProvider(n=2200)
    )

    assert summary.n_trials == 24
    assert summary.missing_price_data == []
    assert summary.leg_size == 3
    assert summary.n_panel_rows > 0
    assert summary.panel_start is not None and summary.panel_end is not None
    assert summary.n_bad_prints_scrubbed == 1
    assert summary.bad_prints_by_ticker == {"CPER": 1}
    assert np.isfinite(summary.effective_breadth)
    assert 1.0 < summary.effective_breadth <= len(COMMODITIES_UNIVERSE)
    assert summary.max_pair is not None
    assert summary.excluded_redundant == COMMODITIES_EXCLUDED_REDUNDANT
    assert summary.text and "24" in summary.text
    assert "carry" in summary.text.lower()
    assert "COST DISCLOSURE" in summary.text

    assert summary.results, "the pipeline produced no results"
    for r in summary.results:
        # This family's OWN n_trials, never pooled with another family's.
        assert r.deflated_sharpe.n_trials == 24
        assert np.isfinite(r.sharpe_annualized)
        assert r.n_trading_days >= 60
        assert r.n_formations > 0
        assert r.deflated_sharpe.dsr_floor_met is True
        assert r.deflated_sharpe.dsr is not None
        # Both cost components must reach every replay: financing accrues on
        # every held day, turnover cost on every formation.
        assert r.total_financing_drag > 0.0
        assert r.total_cost_drag > 0.0

    # The momentum-vs-value correlation AMP predict is negative must at
    # least be MEASURED and reported, whatever its sign on synthetic data.
    assert any({"momentum", "reversal"} == set(pair) for pair in summary.signal_kind_correlations)


def test_screening_survives_a_provider_that_returns_nothing():
    class _EmptyProvider:
        def get_daily_ohlcv(self, tickers, start, end):
            return {}, list(tickers)

    summary = run_commodities_screening(end=date(2020, 1, 1), provider=_EmptyProvider())
    assert summary.results == []
    assert summary.n_trials == 24
    assert summary.n_panel_rows == 0
    assert summary.warnings


def test_screening_respects_a_caller_supplied_start_as_formation_start(monkeypatch):
    captured: list = []

    def fake_screen(data, specs, config, membership_fn=None):
        captured.append(config.formation_start)
        return []

    monkeypatch.setattr(cmod, "screen_cross_sectional_universe", fake_screen)
    run_commodities_screening(
        end=date(2018, 12, 31), start=date(2017, 6, 1), provider=_SyntheticProvider(n=300)
    )
    assert captured[-1] == date(2017, 6, 1)


# --- structural separation from the curve collector -------------------------


def test_family_module_and_curve_collector_are_structurally_separate():
    """The forward-looking curve collector must not be able to bias (or be
    biased by) the screened family: neither module imports the other, in
    either direction."""
    import inspect

    import app.services.research_lab.futures_curve_collector as collector_mod

    def import_lines(source: str) -> list[str]:
        return [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]

    family_imports = import_lines(inspect.getsource(cmod))
    collector_imports = import_lines(inspect.getsource(collector_mod))
    assert not any("futures_curve_collector" in line for line in family_imports), (
        "the commodities family must not import the curve collector"
    )
    assert not any("cross_sectional" in line for line in collector_imports), (
        "the curve collector must not import any cross_sectional module"
    )
