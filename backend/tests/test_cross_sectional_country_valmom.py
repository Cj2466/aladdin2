from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional import (
    CrossSectionalBacktestResult,
    CrossSectionalData,
    FormationRecord,
    run_cross_sectional_backtest,
)
from app.services.research_lab.cross_sectional_country_valmom import (
    COUNTRY_ETF_TICKERS,
    COUNTRY_LOOKBACK_DAYS,
    CVM_CONSTRUCTIONS,
    CVM_HOLDING_DAYS,
    CVM_N_BASE_SPECS,
    CVM_N_TRIALS,
    CVM_RANK_WEIGHTED_RANK_FRACTION,
    CVM_TERCILE_RANK_FRACTION,
    LTR_REQUIRED_HISTORY_DAYS,
    MOM_REQUIRED_HISTORY_DAYS,
    _hedge_and_residual_sharpe,
    _rank_transform,
    breakeven_borrow_bps_per_year,
    breakeven_cost_bps,
    build_combo_daily_returns,
    build_country_valmom_family,
    compute_confound_diagnostics,
    equal_weight_basket_returns,
    run_country_valmom_screening,
    signal_ltr_5y,
    signal_mom_2_12,
)


def _frame(n: int, start: str = "2000-01-03", **series: list[float]) -> pd.DataFrame:
    index = pd.bdate_range(start, periods=n)
    return pd.DataFrame(series, index=index)


def _history(close: pd.DataFrame) -> CrossSectionalData:
    return CrossSectionalData(close=close)


# --- family shape: exactly 15 pre-declared trials --------------------------


def test_family_is_exactly_12_base_specs_and_matches_declared_arithmetic():
    specs = build_country_valmom_family()
    assert len(specs) == CVM_N_BASE_SPECS == 12
    assert CVM_N_TRIALS == 15  # 12 base specs + 3 combinations, per the pre-registration
    assert len({s.pattern_id for s in specs}) == len(specs)


def test_family_covers_every_axis_combination_exactly_once():
    specs = build_country_valmom_family()
    seen = set()
    for s in specs:
        signal = "mom_2_12" if "mom_2_12" in s.pattern_id else "ltr_5y"
        construction = "rank_weighted" if "rank_weighted" in s.pattern_id else "ls_tercile"
        seen.add((signal, s.holding_days, construction))
    assert len(seen) == 12
    assert seen == {
        (signal, holding, construction)
        for signal in ("mom_2_12", "ltr_5y")
        for holding in CVM_HOLDING_DAYS
        for construction in CVM_CONSTRUCTIONS
    }


def test_ls_tercile_specs_are_equal_weighted_terciles_of_five():
    specs = build_country_valmom_family()
    tercile_specs = [s for s in specs if "ls_tercile" in s.pattern_id]
    assert len(tercile_specs) == 6
    for s in tercile_specs:
        assert s.rank_fraction == CVM_TERCILE_RANK_FRACTION
        assert s.leg_weighting == "equal"
        assert s.portfolio == "long_short"
        n_leg = max(1, int(len(COUNTRY_ETF_TICKERS) * s.rank_fraction))
        assert n_leg == 5


def test_rank_weighted_specs_use_magnitude_on_rank_and_half_splits():
    specs = build_country_valmom_family()
    rw_specs = [s for s in specs if "rank_weighted" in s.pattern_id]
    assert len(rw_specs) == 6
    for s in rw_specs:
        assert s.rank_fraction == CVM_RANK_WEIGHTED_RANK_FRACTION
        assert s.leg_weighting == "magnitude"
        n_leg = max(1, int(len(COUNTRY_ETF_TICKERS) * s.rank_fraction))
        assert n_leg == 7


def test_every_spec_shares_the_family_max_lookback():
    specs = build_country_valmom_family()
    assert all(s.lookback_days == COUNTRY_LOOKBACK_DAYS for s in specs)
    assert COUNTRY_LOOKBACK_DAYS == max(MOM_REQUIRED_HISTORY_DAYS, LTR_REQUIRED_HISTORY_DAYS)
    assert COUNTRY_LOOKBACK_DAYS == LTR_REQUIRED_HISTORY_DAYS  # the value leg is the binding one


def test_universe_is_exactly_fifteen_and_pattern_ids_avoid_excluded_tickers():
    assert len(COUNTRY_ETF_TICKERS) == 15
    assert "PGAL" not in COUNTRY_ETF_TICKERS
    assert "ENOR" not in COUNTRY_ETF_TICKERS
    assert "EDEN" not in COUNTRY_ETF_TICKERS
    assert "SPY" in COUNTRY_ETF_TICKERS


# --- signal correctness -----------------------------------------------------


def test_mom_2_12_ranks_the_recent_winner_above_the_recent_loser():
    n = MOM_REQUIRED_HISTORY_DAYS + 5
    winner = np.concatenate([np.full(n - 22, 100.0), np.linspace(100.0, 150.0, 22)])
    loser = np.concatenate([np.full(n - 22, 100.0), np.linspace(100.0, 60.0, 22)])
    # Both move ONLY inside the skipped last month, so their t-12mo..t-1mo
    # window (the only thing mom_2_12 reads) is flat and equal for both —
    # this asserts the skip is real, not merely a slower version of "buy
    # whatever went up in the last N days".
    close = _frame(n, winner=winner, loser=loser)
    signal = signal_mom_2_12(_history(close))
    assert signal["winner"] == pytest.approx(signal["loser"])


def test_mom_2_12_reads_the_twelve_to_one_month_window_not_the_skipped_month():
    n = MOM_REQUIRED_HISTORY_DAYS + 1
    # Winner rises steadily from day 0 to day n-22 (inside the scored
    # window), flat for the skipped last month; loser is the mirror image.
    winner_scored = np.linspace(100.0, 200.0, n - 21)
    winner = np.concatenate([winner_scored, np.full(21, winner_scored[-1])])
    loser_scored = np.linspace(100.0, 50.0, n - 21)
    loser = np.concatenate([loser_scored, np.full(21, loser_scored[-1])])
    close = _frame(n, winner=winner, loser=loser)
    signal = signal_mom_2_12(_history(close))
    assert signal["winner"] > signal["loser"]
    assert signal["winner"] == pytest.approx(1.0, abs=0.02)  # ~ +100% over the scored window


def test_mom_2_12_is_nan_below_required_history():
    close = _frame(MOM_REQUIRED_HISTORY_DAYS - 1, a=np.linspace(100, 110, MOM_REQUIRED_HISTORY_DAYS - 1))
    signal = signal_mom_2_12(_history(close))
    assert signal.isna().all()


def test_ltr_5y_scores_a_big_multiyear_loser_above_a_big_winner():
    n = LTR_REQUIRED_HISTORY_DAYS + 5
    # loser: was expensive ~5y ago, cheap now (positive log-ratio -> long leg)
    loser = np.linspace(200.0, 50.0, n)
    # winner: was cheap ~5y ago, expensive now (negative log-ratio -> short leg)
    winner = np.linspace(50.0, 200.0, n)
    close = _frame(n, loser=loser, winner=winner)
    signal = signal_ltr_5y(_history(close))
    assert signal["loser"] > 0
    assert signal["winner"] < 0
    assert signal["loser"] > signal["winner"]


def test_ltr_5y_is_nan_below_required_history():
    n = LTR_REQUIRED_HISTORY_DAYS - 1
    close = _frame(n, a=np.linspace(100, 110, n))
    signal = signal_ltr_5y(_history(close))
    assert signal.isna().all()


def test_ltr_5y_refuses_a_window_with_too_much_missing_coverage():
    n = LTR_REQUIRED_HISTORY_DAYS + 5
    prices = np.linspace(100.0, 150.0, n)
    close = _frame(n, sparse=prices.copy(), dense=prices.copy())
    # Blank out most of the averaging window for one ticker only.
    window_start = n - 1 - 1386
    window_end = n - 1134
    col = close["sparse"].to_numpy().copy()
    col[window_start : window_end - 5] = np.nan  # leaves < 80% coverage
    close["sparse"] = col
    signal = signal_ltr_5y(_history(close))
    assert np.isnan(signal["sparse"])
    assert np.isfinite(signal["dense"])


# --- rank transform: order-preserving, changes only within-leg weight ------


def test_rank_transform_preserves_ordering_of_the_base_signal():
    n = MOM_REQUIRED_HISTORY_DAYS + 1
    prices = {t: np.linspace(90.0 + 3 * i, 90.0 + 3 * i + 20, n) for i, t in enumerate("ABCDE")}
    close = _frame(n, **prices)
    history = _history(close)
    raw = signal_mom_2_12(history)
    ranked = _rank_transform(signal_mom_2_12)(history)
    assert list(raw.sort_values().index) == list(ranked.sort_values().index)


def test_rank_transform_keeps_nan_as_nan():
    n = MOM_REQUIRED_HISTORY_DAYS + 1
    close = _frame(n, a=np.linspace(100, 120, n))
    ranked = _rank_transform(signal_mom_2_12)(_history(close))
    # Only one ticker in this frame at all — rank of a single valid value
    # is well-defined (1.0), but a genuinely NaN base signal must stay NaN.
    too_short = _frame(MOM_REQUIRED_HISTORY_DAYS - 1, a=np.linspace(100, 120, MOM_REQUIRED_HISTORY_DAYS - 1))
    ranked_short = _rank_transform(signal_mom_2_12)(_history(too_short))
    assert ranked_short.isna().all()


# --- combination series ------------------------------------------------


def test_combo_is_the_equal_weighted_average_on_the_common_intersection():
    idx1 = pd.bdate_range("2020-01-01", periods=10)
    idx2 = pd.bdate_range("2020-01-08", periods=10)  # offset, partial overlap
    mom = CrossSectionalBacktestResult(status="ok", daily_returns=pd.Series(0.01, index=idx1))
    ltr = CrossSectionalBacktestResult(status="ok", daily_returns=pd.Series(-0.02, index=idx2))
    combo = build_combo_daily_returns(mom, ltr)
    overlap = idx1.intersection(idx2)
    assert len(combo) == len(overlap)
    assert combo.iloc[0] == pytest.approx(0.5 * (0.01 - 0.02))


# --- confound diagnostics: hedge mechanics ----------------------------------


def test_hedge_and_residual_sharpe_zeroes_out_a_perfect_replica():
    idx = pd.bdate_range("2015-01-01", periods=300)
    rng = np.random.default_rng(3)
    x = pd.Series(rng.normal(0, 0.01, len(idx)), index=idx)
    y = x.copy()  # a perfect replica of the single factor
    betas, residual_sharpe, n = _hedge_and_residual_sharpe(y, {"basket": x})
    assert betas["basket"] == pytest.approx(1.0, abs=1e-6)
    assert residual_sharpe == 0.0  # degeneracy guard, not a large spurious number
    assert n == len(idx)


def test_hedge_and_residual_sharpe_leaves_an_independent_stream_untouched():
    idx = pd.bdate_range("2015-01-01", periods=500)
    rng = np.random.default_rng(4)
    x = pd.Series(rng.normal(0, 0.01, len(idx)), index=idx)
    y = pd.Series(0.001 + rng.normal(0, 0.01, len(idx)), index=idx)  # independent of x, own positive drift
    betas, residual_sharpe, n = _hedge_and_residual_sharpe(y, {"basket": x})
    assert abs(betas["basket"]) < 0.2
    assert residual_sharpe > 0  # the drift survives hedging an unrelated factor


def test_equal_weight_basket_returns_is_the_plain_cross_sectional_mean():
    close = _frame(5, a=[100, 101, 102, 101, 103], b=[50, 49, 50, 51, 52])
    basket = equal_weight_basket_returns(close)
    a_ret = close["a"].pct_change()
    b_ret = close["b"].pct_change()
    expected = (a_ret + b_ret) / 2.0
    pd.testing.assert_series_equal(basket, expected, check_names=False)


# --- breakeven helpers -------------------------------------------------


def test_breakeven_cost_is_none_when_nothing_was_ever_charged():
    idx = pd.bdate_range("2020-01-01", periods=100)
    replay = CrossSectionalBacktestResult(status="ok", daily_returns=pd.Series(0.001, index=idx), total_cost=0.0)
    assert breakeven_cost_bps(replay, 10.0) is None


def test_breakeven_cost_scales_with_the_ratio_of_gross_to_charged():
    idx = pd.bdate_range("2020-01-01", periods=100)
    # net = 0.0005/day, cost charged totals 0.01 -> gross = net_total + cost
    net = pd.Series(0.0005, index=idx)
    replay = CrossSectionalBacktestResult(status="ok", daily_returns=net, total_cost=0.01)
    be = breakeven_cost_bps(replay, cost_bps_used=10.0)
    gross_total = float(net.sum()) + 0.01
    assert be == pytest.approx(10.0 * gross_total / 0.01)


def test_breakeven_borrow_is_none_for_a_too_short_series():
    idx = pd.bdate_range("2020-01-01", periods=1)
    replay = CrossSectionalBacktestResult(status="ok", daily_returns=pd.Series(0.001, index=idx))
    assert breakeven_borrow_bps_per_year(replay) is None


# --- confound diagnostics end-to-end on a tiny synthetic replay -------------


def test_confound_diagnostics_run_without_error_on_a_minimal_replay():
    idx = pd.bdate_range("2015-01-01", periods=400)
    rng = np.random.default_rng(7)
    daily = pd.Series(rng.normal(0.0002, 0.01, len(idx)), index=idx)
    formations = [
        FormationRecord(date=idx[i], n_eligible=15, long_tickers=["EWA", "EWC"], short_tickers=["EWJ", "EWU"], turnover=0.5)
        for i in range(0, 380, 21)
    ]
    replay = CrossSectionalBacktestResult(status="ok", daily_returns=daily, formations=formations, total_cost=0.02)
    close = _frame(400, start="2015-01-01", **{t: 100 + rng.normal(0, 1, 400).cumsum() for t in COUNTRY_ETF_TICKERS})
    basket = equal_weight_basket_returns(close)
    dxy = pd.Series(100 + rng.normal(0, 0.2, 400).cumsum(), index=idx)
    uup = pd.Series(25 + rng.normal(0, 0.1, 400).cumsum(), index=idx[100:] if False else idx)

    diag = compute_confound_diagnostics("test_spec", replay, 21, close, basket, dxy, uup)
    assert diag.pattern_id == "test_spec"
    assert np.isfinite(diag.basket_beta)
    assert np.isfinite(diag.dxy_beta)
    assert diag.n_nonoverlapping_formations == len(formations)
    assert diag.bootstrap_p_value is not None
    assert diag.static_tilt_sharpe is not None
    assert diag.top2_block_share_of_gross is not None


# --- offline end-to-end pipeline -------------------------------------------


class _SyntheticProvider:
    """Generates a plausible-looking, deterministic random-walk close panel
    for WHATEVER tickers are requested — the country universe, and the
    DX-Y.NYB / UUP dollar-factor proxies alike — so the full screening
    pipeline can be pipeline-tested offline. Small and synthetic on
    purpose: a wiring check, never a source of conclusions."""

    def __init__(self, n: int = 2600, seed: int = 20260904):
        self.n = n
        self.seed = seed

    def get_daily_ohlcv(self, tickers, start, end):
        index = pd.bdate_range("2000-01-03", periods=self.n)
        close = {}
        for i, t in enumerate(tickers):
            rng = np.random.default_rng(self.seed + i)
            close[t] = 100.0 * np.cumprod(1 + rng.normal(0.0002, 0.01, self.n))
        return {"close": pd.DataFrame(close, index=index)}, []


def test_screening_runs_end_to_end_offline_and_produces_all_fifteen_trials():
    provider = _SyntheticProvider()
    summary = run_country_valmom_screening(end=date(2026, 9, 2), provider=provider)

    assert summary.n_trials == 15
    assert summary.missing_price_data == []
    assert len(summary.results) == 15
    assert summary.panel_start is not None and summary.panel_end is not None
    assert summary.dxy_start is not None and summary.uup_start is not None

    for r in summary.results:
        assert r.deflated_sharpe.n_trials == 15
        assert np.isfinite(r.sharpe_annualized)
        assert r.n_trading_days >= 60
        c = summary.confounds.get(r.pattern_id)
        assert c is not None, f"{r.pattern_id} missing its mandatory confound diagnostic"
        assert np.isfinite(c.basket_beta)
        assert r.pattern_id in summary.raw_returns

    # sensitivity arms cover all three cost levels for the 12 real specs
    for pid, arms in summary.sensitivity_sharpe.items():
        assert 10.0 in arms


def test_screening_uses_fixed_universe_membership_not_the_equity_gate(monkeypatch):
    import app.services.research_lab.cross_sectional_country_valmom as cvmmod

    captured: list = []
    real = run_cross_sectional_backtest

    def spy(data, spec, config, membership_fn=None):
        captured.append(membership_fn)
        return real(data, spec, config, membership_fn)

    monkeypatch.setattr(cvmmod, "run_cross_sectional_backtest", spy)
    provider = _SyntheticProvider(n=1500)  # too short to form -- membership_fn is still captured
    run_country_valmom_screening(end=date(2010, 1, 1), provider=provider)
    assert captured, "run_cross_sectional_backtest was never called"
    membership_fn = captured[0]
    for ticker in COUNTRY_ETF_TICKERS:
        assert membership_fn(ticker, date(2015, 6, 1)) is True
    assert membership_fn("AAPL", date(2015, 6, 1)) is False


def test_screening_survives_a_provider_that_returns_nothing():
    class _EmptyProvider:
        def get_daily_ohlcv(self, tickers, start, end):
            return {}, list(tickers)

    summary = run_country_valmom_screening(end=date(2026, 9, 2), provider=_EmptyProvider())
    assert summary.results == []
    assert summary.n_panel_rows == 0
    assert summary.warnings
