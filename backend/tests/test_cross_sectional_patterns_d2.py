from datetime import date

import numpy as np
import pandas as pd
import pytest

import app.services.research_lab.cross_sectional_patterns_d2 as d2
from app.services.research_lab.cross_sectional import (
    DEFAULT_IMPUTED_DELISTING_RETURN,
    CrossSectionalConfig,
    CrossSectionalData,
)
from app.services.research_lab.cross_sectional_patterns_d2 import (
    D2_COHORT_FORMATION_DAYS,
    D2_FAMILY,
    D2_HOLDING_DAYS,
    D2_N_TRIALS,
    compute_d2_independent_window_disclosure,
    screen_d2_reversal_family,
    signal_long_horizon_reversal,
)


def _frame(values_by_ticker: dict[str, list[float]], start: str = "2020-01-02") -> pd.DataFrame:
    n = len(next(iter(values_by_ticker.values())))
    return pd.DataFrame(values_by_ticker, index=pd.bdate_range(start, periods=n))


# --- family shape: exactly these 4, no more, no fewer ---------------------

EXPECTED_PATTERN_IDS = {
    "d2_reversal_long_short_l756",
    "d2_reversal_long_short_l504",
    "d2_reversal_long_universe_hedged_l756",
    "d2_reversal_long_universe_hedged_l504",
}


def test_family_is_exactly_4_definitions():
    assert len(D2_FAMILY) == 4
    assert D2_N_TRIALS == 4


def test_family_pattern_ids_are_exactly_the_expected_4_and_no_others():
    ids = {s.pattern_id for s in D2_FAMILY}
    assert ids == EXPECTED_PATTERN_IDS
    assert len([s.pattern_id for s in D2_FAMILY]) == 4  # no duplicates collapsed above


def test_family_covers_both_axes():
    portfolios = {s.portfolio for s in D2_FAMILY}
    lookbacks = {s.lookback_days for s in D2_FAMILY}
    assert portfolios == {"long_short", "long_universe_hedged"}
    assert lookbacks == {756, 504}
    # Every (portfolio, lookback) combination appears exactly once.
    combos = {(s.portfolio, s.lookback_days) for s in D2_FAMILY}
    assert len(combos) == 4


def test_family_every_spec_is_cited_and_shares_the_common_parameters():
    for spec in D2_FAMILY:
        assert spec.citation  # every definition traces to a real source
        assert "De Bondt" in spec.citation
        assert spec.holding_days == D2_HOLDING_DAYS == 756
        assert spec.cohort_formation_days == D2_COHORT_FORMATION_DAYS == 63
        assert spec.rank_fraction == pytest.approx(0.2)  # quintiles, not deciles
        assert spec.family == "long_horizon_price_reversal"
        assert not spec.requires_open and not spec.requires_volume and not spec.requires_market_cap
        assert spec.leg_weighting == "magnitude"  # this family never opts into value-weighting


def test_family_never_pooled_with_round_c_or_round_d_pattern_ids():
    # This family's own pattern_ids must not collide with any other
    # family's — a collision would risk silent cross-family confusion
    # downstream (e.g. a caller indexing screening results by pattern_id
    # across multiple families).
    from app.services.research_lab.cross_sectional_patterns import ROUND_C_FAMILY
    from app.services.research_lab.cross_sectional_patterns_round_d import (
        ROUND_D_LPS_INTRADAY_FAMILY,
    )

    d2_ids = {s.pattern_id for s in D2_FAMILY}
    other_ids = {s.pattern_id for s in ROUND_C_FAMILY} | {s.pattern_id for s in ROUND_D_LPS_INTRADAY_FAMILY}
    assert d2_ids.isdisjoint(other_ids)


# --- signal_long_horizon_reversal ------------------------------------------


def test_signal_reverses_direction_losers_score_higher_than_winners():
    # WINNER doubles over the window (+100% raw return); LOSER halves
    # (-50% raw return). The signal is the NEGATED cumulative return, so
    # the loser must score HIGHER (it belongs in the long leg) and the
    # winner LOWER (short leg) — De Bondt & Thaler's own reversal
    # direction, exercised through this harness's top-is-long convention.
    n = 800
    winner = np.linspace(100.0, 200.0, n).tolist()
    loser = np.linspace(100.0, 50.0, n).tolist()
    data = CrossSectionalData(close=_frame({"WINNER": winner, "LOSER": loser}))
    signal = signal_long_horizon_reversal(data, lookback_days=756)
    assert signal["LOSER"] > signal["WINNER"]
    assert signal["LOSER"] > 0.0  # a real loser has a positive (long-favoring) signal
    assert signal["WINNER"] < 0.0  # a real winner has a negative (short-favoring) signal


def test_signal_hand_check_matches_negated_two_point_cumulative_return():
    n = 800
    prices = np.linspace(50.0, 80.0, n)  # +60% over the window
    data = CrossSectionalData(close=_frame({"A": prices.tolist()}))
    signal = signal_long_horizon_reversal(data, lookback_days=756)
    window = prices[-756:]
    expected = -((window[-1] / window[0]) - 1.0)
    assert signal["A"] == pytest.approx(expected)


def test_signal_is_nan_for_a_recently_listed_ticker_with_no_window_start_price():
    # IPO recency: OLD has a real price the full 756 days back; RECENT only
    # has ~200 days of history, so its window-start price is NaN and the
    # two-point cumulative return (hence the signal) must be NaN too — no
    # extra guard code needed for this case, see the module docstring.
    n = 800
    old = np.linspace(50.0, 100.0, n).tolist()
    recent = [np.nan] * (n - 200) + np.linspace(90.0, 100.0, 200).tolist()
    data = CrossSectionalData(close=_frame({"OLD": old, "RECENT": recent}))
    signal = signal_long_horizon_reversal(data, lookback_days=756)
    assert np.isfinite(signal["OLD"])
    assert np.isnan(signal["RECENT"])


def test_signal_refuses_a_gappy_interior_even_with_both_endpoints_present():
    # SPARSE has a real price at both window endpoints but almost nothing
    # in between (a data-quality problem, not an IPO) — the secondary
    # MIN_SIGNAL_OBS_FRACTION guard must still refuse it.
    n = 800
    full = np.linspace(50.0, 100.0, n).tolist()
    sparse = [np.nan] * n
    sparse[-756] = 90.0  # window-start endpoint
    sparse[-1] = 95.0  # window-end endpoint (formation day)
    data = CrossSectionalData(close=_frame({"FULL": full, "SPARSE": sparse}))
    signal = signal_long_horizon_reversal(data, lookback_days=756)
    assert np.isfinite(signal["FULL"])
    assert np.isnan(signal["SPARSE"])


# --- compute_d2_independent_window_disclosure ------------------------------


def test_disclosure_exact_multiple_of_holding_days_has_no_partial_window():
    disclosure = compute_d2_independent_window_disclosure(3 * 756, holding_days=756)
    assert disclosure.n_full_independent_windows == 3
    assert disclosure.partial_window_fraction == pytest.approx(0.0)


def test_disclosure_reports_the_honest_3_to_4_window_count_for_the_real_history_span():
    # ~11.6 years of usable point-in-time history at the conventional
    # 252-trading-day year is ~2931 trading days — the real figure this
    # family's audited history span produces (see module docstring's "THE
    # SMALL-SAMPLE PROBLEM" section): 3 full 756-day windows plus a
    # partial ~88% of a fourth, i.e. "3-4" independent windows, never the
    # retracted 7-8 claim.
    disclosure = compute_d2_independent_window_disclosure(2931, holding_days=756)
    assert disclosure.n_full_independent_windows == 3
    assert disclosure.partial_window_fraction == pytest.approx(663 / 756, abs=1e-6)
    assert "3" in disclosure.text and "4" in disclosure.text
    assert "7-8" in disclosure.text  # names and retracts the earlier wrong claim
    assert "756" in disclosure.text
    assert str(D2_N_TRIALS) in disclosure.text  # discloses the SEPARATE n_trials caution too


def test_disclosure_zero_trading_days_does_not_divide_by_zero():
    disclosure = compute_d2_independent_window_disclosure(0, holding_days=756)
    assert disclosure.n_full_independent_windows == 0
    assert disclosure.partial_window_fraction == pytest.approx(0.0)


# --- screen_d2_reversal_family (production entry point, offline) ----------


def test_screening_rejects_start_before_membership_coverage():
    with pytest.raises(ValueError, match="predates point-in-time membership"):
        screen_d2_reversal_family(date(2014, 1, 1), date(2020, 1, 1))


def test_default_config_opts_into_delisting_imputation_but_explicit_config_is_respected(monkeypatch):
    # screen_d2_reversal_family's OWN default (config=None) must enable the
    # harness's generic opt-in delisting-imputation flag (see module
    # docstring's "DELISTING RETURNS" section) — but a caller-supplied
    # config must be used exactly as given, never silently overridden.
    captured: list[CrossSectionalConfig] = []

    def fake_screen(data, specs, config, membership_fn=None):
        captured.append(config)
        return []

    monkeypatch.setattr(d2, "screen_cross_sectional_universe", fake_screen)
    provider = _FakeProvider(_STALWART_MEMBERS)

    screen_d2_reversal_family(date(2020, 1, 6), date(2021, 1, 1), provider=provider, config=None)
    assert captured[-1].impute_delisting_returns is True
    assert captured[-1].imputed_delisting_return == pytest.approx(DEFAULT_IMPUTED_DELISTING_RETURN)

    explicit = CrossSectionalConfig(min_names_per_leg=1)  # impute_delisting_returns left at its own False default
    screen_d2_reversal_family(date(2020, 1, 6), date(2021, 1, 1), provider=provider, config=explicit)
    assert captured[-1] is explicit
    assert captured[-1].impute_delisting_returns is False


class _FakeProvider:
    """Synthetic-data stand-in for YFinanceProvider.get_daily_ohlcv — the
    same aligned three-frame contract, no network (mirrors Round C/D's own
    test fixture)."""

    def __init__(self, tickers_expected_member: list[str], seed: int = 23):
        self.tickers = tickers_expected_member
        self.seed = seed
        self.requested: list[str] | None = None

    def get_daily_ohlcv(self, tickers, start, end):
        self.requested = list(tickers)
        rng = np.random.default_rng(self.seed)
        index = pd.bdate_range(start, end)
        served = [t for t in tickers if t in self.tickers]
        close = pd.DataFrame(
            {t: 100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.015, len(index))) for t in served},
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
# removed) — same list Round C/D's own smoke tests use, so the real
# was_member keeps every one eligible at every formation date and the
# pipeline test isolates mechanics, not membership.
_STALWART_MEMBERS = [
    "AAPL", "MSFT", "JPM", "JNJ", "KO", "PG", "XOM", "WMT", "MCD", "HD", "CAT", "MMM",
]


def test_screening_runs_end_to_end_against_a_fake_provider():
    """Offline end-to-end pipeline check: real universe construction
    (get_universe_over), real membership gating (was_member), the full
    4-definition family, synthetic prices spanning enough history for
    D2's own 756-day hold to realize. Small on purpose — the smoke test of
    pipeline correctness, never a source of conclusions."""
    provider = _FakeProvider(_STALWART_MEMBERS)
    config = CrossSectionalConfig(min_names_per_leg=1, impute_delisting_returns=True)
    summary = screen_d2_reversal_family(
        date(2016, 1, 6), date(2023, 6, 30), provider=provider, config=config
    )

    assert provider.requested is not None
    assert len(provider.requested) > 550  # union universe over the window, not today's snapshot
    assert set(_STALWART_MEMBERS) <= set(provider.requested)
    assert set(summary.missing_price_data) == set(provider.requested) - set(_STALWART_MEMBERS)

    assert summary.results  # the pipeline produced sane-shaped output
    for r in summary.results:
        assert r.deflated_sharpe.n_trials == 4  # this family's own n_trials, never Round C's 30
        assert np.isfinite(r.sharpe_annualized)
        assert r.n_trading_days >= 60
        assert r.n_formations > 0
        # n_trials=4 is below MIN_TRIALS_FOR_DSR=5 (see deflated_sharpe.py):
        # the DSR proper must not compute, only PSR-vs-zero.
        assert r.deflated_sharpe.dsr_floor_met is False
        assert r.deflated_sharpe.dsr is None
        assert r.deflated_sharpe.psr_vs_zero is not None

    disclosure = summary.independent_window_disclosure
    assert disclosure.n_trading_days_replayed > 0
    assert disclosure.holding_days == 756
    # This synthetic window (~7.5 years replay after ~4.1-year lookback
    # warmup) cannot possibly contain more than a handful of independent
    # 756-day cycles — nowhere near the retracted 7-8 claim.
    assert 0 <= disclosure.n_full_independent_windows <= 4
