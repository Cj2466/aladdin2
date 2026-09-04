from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional import (
    DEFAULT_XS_COST_BPS,
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    screen_cross_sectional_universe,
)
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.cross_sectional_ivol import (
    IVOL_LOOKBACK_DAYS,
    IVOL_RANK_FRACTION,
    ROUND_D1_FAMILY,
    SP500_MAX_PLAUSIBLE_MARKET_CAP_USD,
    SP500_MIN_PLAUSIBLE_MARKET_CAP_USD,
    implausible_market_cap_mask,
    restrict_share_counts_to_price_lifecycle,
    signal_idiosyncratic_volatility,
)
from app.services.research_lab.cross_sectional_patterns import (
    CGO_LOOKBACK_DAYS,
    ROUND_C_FAMILY,
    signal_52_week_high_nearness,
    signal_capital_gains_overhang,
)
from app.services.research_lab.cross_sectional_small_mid_cap import (
    DISPOSITION_N_TRIALS,
    IVOL_N_TRIALS,
    REUSED_DISPOSITION_FAMILY_SIZE,
    REUSED_IVOL_FAMILY_SIZE,
    SMALL_CAP_COST_BPS,
    SMALL_CAP_DISPOSITION_FAMILY,
    SMALL_CAP_HOLDING_DAYS,
    SMALL_CAP_IVOL_FAMILY,
    SMALL_CAP_MAX_PLAUSIBLE_MARKET_CAP_USD,
    SMALL_CAP_MIN_PLAUSIBLE_MARKET_CAP_USD,
    UNIVERSE_MULTIPLIER,
    default_small_cap_config,
    mask_recycled_ticker_prices,
    run_small_cap_disposition_screening,
    run_small_cap_ivol_screening,
)


def _frame(values_by_ticker: dict[str, list[float]], start: str = "2018-01-01") -> pd.DataFrame:
    n = len(next(iter(values_by_ticker.values())))
    return pd.DataFrame(values_by_ticker, index=pd.bdate_range(start, periods=n))


# =====================================================================
# THE DOUBLED n_trials -- this build's central statistical claim
# =====================================================================


def test_n_trials_is_exactly_double_each_reused_familys_own_size():
    # The universe is a searched dimension: re-running an N-definition family
    # on a second universe makes the reportable configuration set N x 2. See
    # the module docstring's section 2.
    assert UNIVERSE_MULTIPLIER == 2
    assert REUSED_IVOL_FAMILY_SIZE == 21
    assert REUSED_DISPOSITION_FAMILY_SIZE == 18
    assert IVOL_N_TRIALS == 42
    assert DISPOSITION_N_TRIALS == 36
    assert IVOL_N_TRIALS == UNIVERSE_MULTIPLIER * REUSED_IVOL_FAMILY_SIZE
    assert DISPOSITION_N_TRIALS == UNIVERSE_MULTIPLIER * REUSED_DISPOSITION_FAMILY_SIZE


def test_reused_family_sizes_are_read_from_the_real_upstream_families():
    # Not hand-typed literals: if either upstream family is ever edited, this
    # module's n_trials arithmetic must break loudly rather than go stale.
    assert REUSED_IVOL_FAMILY_SIZE == len(ROUND_D1_FAMILY)
    disposition = [
        s
        for s in ROUND_C_FAMILY
        if s.family in ("disposition_52wk_high", "disposition_capital_gains_overhang")
    ]
    assert REUSED_DISPOSITION_FAMILY_SIZE == len(disposition) == 18
    # ...and the excluded third group really is Round C's remaining 12.
    assert len(ROUND_C_FAMILY) - len(disposition) == 12


def test_n_trials_is_larger_than_the_number_of_specs_actually_run():
    # Deliberately NOT shrunk to 2 x (specs replayed) = 28 / 24. The hold
    # restriction removes specs from THIS replay; it does not un-search the
    # definitions that produced the family. Shrinking would be the
    # trial-count laundering cross_sectional_patterns_round_d.py rejects.
    assert IVOL_N_TRIALS > len(SMALL_CAP_IVOL_FAMILY)
    assert DISPOSITION_N_TRIALS > len(SMALL_CAP_DISPOSITION_FAMILY)
    assert IVOL_N_TRIALS > UNIVERSE_MULTIPLIER * len(SMALL_CAP_IVOL_FAMILY)
    assert DISPOSITION_N_TRIALS > UNIVERSE_MULTIPLIER * len(SMALL_CAP_DISPOSITION_FAMILY)


def _synthetic_panel(n_rows: int, n_tickers: int, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    tickers = [f"T{i:03d}" for i in range(n_tickers)]
    closes, volumes = {}, {}
    for t in tickers:
        closes[t] = (100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.02, n_rows))).tolist()
        volumes[t] = rng.lognormal(13, 0.4, n_rows).tolist()
    return _frame(closes), _frame(volumes)


def test_the_doubled_n_trials_actually_reaches_the_dsr_end_to_end():
    # The build's requirement is that the doubled count is ASSERTED IN CODE
    # and used, not merely claimed in prose. This drives the real family
    # through the real screening call and reads n_trials back off every
    # DeflatedSharpeResult it produced.
    close, volume = _synthetic_panel(1000, 40, seed=11)
    data = CrossSectionalData(close=close, volume=volume)
    config = CrossSectionalConfig(
        cost_bps=SMALL_CAP_COST_BPS, formation_start=close.index[600].date()
    )
    results = screen_cross_sectional_universe(
        data,
        SMALL_CAP_DISPOSITION_FAMILY,
        config,
        membership_fn=lambda _t, _d: True,
        n_trials_override=DISPOSITION_N_TRIALS,
    )
    assert results
    for r in results:
        assert r.deflated_sharpe.n_trials == DISPOSITION_N_TRIALS == 36
        # ...and emphatically not the number of specs in the replayed list.
        assert r.deflated_sharpe.n_trials != len(SMALL_CAP_DISPOSITION_FAMILY)


def test_screening_refuses_an_override_that_shrinks_the_denominator():
    # There is no legitimate reason to pass a smaller n_trials, so the
    # parameter must not be able to express one.
    close, _volume = _synthetic_panel(400, 20, seed=3)
    data = CrossSectionalData(close=close)
    spec = CrossSectionalSpec(
        pattern_id="p",
        family="f",
        citation="c",
        signal_fn=lambda h: h.close.iloc[-1],
        lookback_days=20,
        holding_days=21,
        portfolio="long_short",
        rank_fraction=0.2,
    )
    config = CrossSectionalConfig(formation_start=close.index[30].date())
    with pytest.raises(ValueError, match="laundering"):
        screen_cross_sectional_universe(
            data, [spec, spec], config, membership_fn=lambda _t, _d: True, n_trials_override=1
        )


def test_default_screening_behavior_is_unchanged_without_an_override():
    # Every family screened before n_trials_override existed must be
    # byte-for-byte unaffected by its existence.
    close, _volume = _synthetic_panel(500, 25, seed=4)
    data = CrossSectionalData(close=close)
    specs = [
        CrossSectionalSpec(
            pattern_id=f"p{h}",
            family="f",
            citation="c",
            signal_fn=lambda h_: h_.close.iloc[-1] / h_.close.iloc[0],
            lookback_days=60,
            holding_days=h,
            portfolio="long_short",
            rank_fraction=0.2,
        )
        for h in (21, 42, 63)
    ]
    config = CrossSectionalConfig(formation_start=close.index[100].date())
    results = screen_cross_sectional_universe(
        data, specs, config, membership_fn=lambda _t, _d: True
    )
    assert results
    for r in results:
        # POOLED DENOMINATOR (2026-09-04): the family's own declared size is
        # now the FLOOR, not the answer -- global_effective_n.dsr_n_trials
        # raises it to the project-wide effectively-independent trial count
        # when that is larger. Both halves are pinned: the exact pooled value,
        # AND the >= that this test was originally written to protect (a
        # denominator below the declared size is trial-count laundering).
        assert r.deflated_sharpe.n_trials == dsr_n_trials(len(specs))
        assert r.deflated_sharpe.n_trials >= len(specs)


# =====================================================================
# The pre-registered holding-period restriction
# =====================================================================


def test_every_spec_holds_only_for_the_pre_registered_horizons():
    assert SMALL_CAP_HOLDING_DAYS == (126, 252)
    for spec in SMALL_CAP_IVOL_FAMILY + SMALL_CAP_DISPOSITION_FAMILY:
        assert spec.holding_days in SMALL_CAP_HOLDING_DAYS


def test_the_cost_dominated_short_holds_are_absent_entirely():
    # 21 and 63 are excluded by the cost argument BEFORE any result was
    # seen -- not filtered out afterwards.
    holds = {s.holding_days for s in SMALL_CAP_IVOL_FAMILY + SMALL_CAP_DISPOSITION_FAMILY}
    assert 21 not in holds
    assert 63 not in holds
    # The originals really did carry them, so this is a genuine restriction.
    assert 21 in {s.holding_days for s in ROUND_D1_FAMILY}
    assert 21 in {s.holding_days for s in ROUND_C_FAMILY}


def test_family_sizes_are_the_documented_ones():
    assert len(SMALL_CAP_IVOL_FAMILY) == 14
    assert len(SMALL_CAP_DISPOSITION_FAMILY) == 12
    ids = [s.pattern_id for s in SMALL_CAP_IVOL_FAMILY + SMALL_CAP_DISPOSITION_FAMILY]
    assert len(set(ids)) == len(ids)
    assert all(i.startswith("sc600_") for i in ids)


# =====================================================================
# These are the SAME definitions, re-run -- not lookalikes
# =====================================================================


def test_signal_functions_are_the_originals_not_reimplementations():
    # If these were re-implemented here, a "small caps differ from large
    # caps" finding could be an artifact of the re-implementation rather
    # than of the universe. Each spec's partial must wrap the imported
    # function object itself.
    for spec in SMALL_CAP_IVOL_FAMILY:
        assert spec.signal_fn.func is signal_idiosyncratic_volatility
    for spec in SMALL_CAP_DISPOSITION_FAMILY:
        if spec.family == "small_cap_disposition_52wk_high":
            assert spec.signal_fn.func is signal_52_week_high_nearness
        else:
            assert spec.signal_fn.func is signal_capital_gains_overhang


def test_reused_parameters_match_the_originals_exactly():
    # Only holding_days may differ from the source families.
    ivol_lookbacks = {s.signal_fn.keywords["lookback_days"] for s in SMALL_CAP_IVOL_FAMILY}
    assert ivol_lookbacks == set(IVOL_LOOKBACK_DAYS) | {63}
    for spec in SMALL_CAP_IVOL_FAMILY:
        assert spec.rank_fraction == pytest.approx(IVOL_RANK_FRACTION)
        assert spec.leg_weighting == "value"
        assert spec.requires_market_cap is True

    cgo = [s for s in SMALL_CAP_DISPOSITION_FAMILY if "cgo" in s.pattern_id]
    assert {s.signal_fn.keywords["lookback_days"] for s in cgo} == set(CGO_LOOKBACK_DAYS)
    assert all(s.requires_volume for s in cgo)
    gh52 = [s for s in SMALL_CAP_DISPOSITION_FAMILY if "gh52" in s.pattern_id]
    assert {s.rank_fraction for s in gh52} == {0.1, 0.2}
    assert {s.portfolio for s in gh52} == {"long_short", "long_universe_hedged"}


def test_citations_are_carried_over_verbatim():
    for spec in SMALL_CAP_IVOL_FAMILY:
        assert "Ang" in spec.citation and "Bali" in spec.citation and "Blitz" in spec.citation
    for spec in SMALL_CAP_DISPOSITION_FAMILY:
        assert "George" in spec.citation or "Grinblatt" in spec.citation


def test_lou_polk_skouras_is_excluded_entirely():
    # Its own hold axis is {21, 63}; both are ruled out by the cost argument,
    # and extending it would be inventing a definition rather than re-running
    # one.
    assert not any("lps" in s.pattern_id for s in SMALL_CAP_DISPOSITION_FAMILY)
    assert not any(s.requires_open for s in SMALL_CAP_DISPOSITION_FAMILY)


# =====================================================================
# The small-cap cost assumption
# =====================================================================


def test_cost_is_the_small_cap_number_not_the_large_cap_default():
    assert SMALL_CAP_COST_BPS == 15.0
    assert SMALL_CAP_COST_BPS != DEFAULT_XS_COST_BPS
    assert SMALL_CAP_COST_BPS == pytest.approx(3.0 * DEFAULT_XS_COST_BPS)
    assert default_small_cap_config().cost_bps == SMALL_CAP_COST_BPS


def test_default_config_carries_the_cost_and_the_requested_formation_start():
    config = default_small_cap_config(date(2020, 1, 1))
    assert config.cost_bps == SMALL_CAP_COST_BPS
    assert config.formation_start == date(2020, 1, 1)
    # Financing stays at the harness default -- see section 4 on why a
    # fabricated small-cap borrow rate would be worse than a disclosed zero.
    assert config.financing_bps_per_year == 0.0


def test_the_pre_registered_holds_clear_the_cost_hurdle_the_excluded_ones_fail():
    # The section 3 arithmetic, executed rather than only written down: one
    # full long_short reformation trades gross notional 2.0.
    def annual_drag_bps(hold: int) -> float:
        return (252.0 / hold) * 2.0 * SMALL_CAP_COST_BPS

    def sharpe_drag(hold: int, annual_vol: float = 0.10) -> float:
        return (annual_drag_bps(hold) / 10_000.0) / annual_vol

    assert sharpe_drag(21) == pytest.approx(0.36, abs=0.01)
    assert sharpe_drag(63) == pytest.approx(0.12, abs=0.01)
    assert sharpe_drag(126) == pytest.approx(0.06, abs=0.01)
    assert sharpe_drag(252) == pytest.approx(0.03, abs=0.01)
    # Every retained hold costs under a tenth of a Sharpe point; every
    # excluded one costs more.
    for hold in SMALL_CAP_HOLDING_DAYS:
        assert sharpe_drag(hold) < 0.10
    for hold in (21, 63):
        assert sharpe_drag(hold) >= 0.10


# =====================================================================
# Structural recycled-ticker containment
# =====================================================================


def _three_ticker_frames() -> dict[str, pd.DataFrame]:
    n = 300
    close, volume = _synthetic_panel(n, 3, seed=21)
    close.columns = ["STAYS", "RECYCLED", "CLEAN_EXIT"]
    volume.columns = list(close.columns)
    return {"close": close, "volume": volume}


def test_a_wholly_recycled_ticker_is_dropped_outright():
    frames = _three_ticker_frames()
    close = frames["close"]
    exit_ts = close.index[100]
    # RECYCLED has no price at all until well after its index exit -- every
    # row in the frame belongs to the successor company.
    close.loc[close.index <= close.index[200], "RECYCLED"] = np.nan

    def intervals(ticker: str):
        if ticker == "STAYS":
            return [(close.index[0].date(), None)]
        return [(close.index[0].date(), exit_ts.date())]

    cleaned, dropped, truncated = mask_recycled_ticker_prices(frames, intervals)
    assert dropped == ["RECYCLED"]
    assert truncated == []
    assert "RECYCLED" not in cleaned["close"].columns
    # ...and the other frames stay aligned, which
    # validate_cross_sectional_data requires.
    assert list(cleaned["volume"].columns) == list(cleaned["close"].columns)
    assert cleaned["close"].index.equals(cleaned["volume"].index)


def test_a_departed_ticker_is_truncated_at_a_post_exit_gap():
    frames = _three_ticker_frames()
    close = frames["close"]
    exit_ts = close.index[100]
    # CLEAN_EXIT trades through its exit, stops, then a reused symbol
    # reappears after a long gap.
    gap = (close.index > exit_ts) & (close.index < close.index[200])
    close.loc[gap, "CLEAN_EXIT"] = np.nan

    def intervals(ticker: str):
        if ticker == "STAYS":
            return [(close.index[0].date(), None)]
        return [(close.index[0].date(), exit_ts.date())]

    cleaned, dropped, truncated = mask_recycled_ticker_prices(frames, intervals)
    assert "CLEAN_EXIT" in truncated
    assert "CLEAN_EXIT" not in dropped
    tail = cleaned["close"]["CLEAN_EXIT"]
    assert tail.loc[close.index[200] :].isna().all()
    # The legitimate post-removal window before the gap survives -- index
    # removal is not a forced sale (cross_sectional.py's own convention).
    assert tail.loc[exit_ts : close.index[105]].notna().any()


def test_a_still_listed_member_is_never_touched():
    frames = _three_ticker_frames()
    close = frames["close"]

    def intervals(_ticker: str):
        return [(close.index[0].date(), None)]

    cleaned, dropped, truncated = mask_recycled_ticker_prices(frames, intervals)
    assert dropped == [] and truncated == []
    assert cleaned["close"].equals(close)


def test_a_ticker_with_no_recorded_membership_is_never_touched():
    frames = _three_ticker_frames()
    cleaned, dropped, truncated = mask_recycled_ticker_prices(frames, lambda _t: [])
    assert dropped == [] and truncated == []
    assert cleaned["close"].equals(frames["close"])


def test_masking_is_applied_by_the_production_entry_points(monkeypatch):
    # The mask is not an optional post-processing step a caller might forget:
    # both entry points must run it and must RETURN what it removed, since
    # those counts qualify every result.
    import app.services.research_lab.cross_sectional_small_mid_cap as module

    calls: list[int] = []
    real = module.mask_recycled_ticker_prices

    def spy(frames, *args, **kwargs):
        calls.append(1)
        return real(frames, *args, **kwargs)

    monkeypatch.setattr(module, "mask_recycled_ticker_prices", spy)

    close, volume = _synthetic_panel(900, 30, seed=31)
    close.columns = volume.columns = [f"SC{i:03d}" for i in range(30)]
    open_ = close.copy()

    class FakeProvider:
        def get_daily_ohlcv(self, tickers, start, end):
            return {"close": close, "open": open_, "volume": volume}, ["GONE"]

    monkeypatch.setattr(module, "get_universe_over", lambda s, e: list(close.columns))
    monkeypatch.setattr(module, "was_member", lambda _t, _d: True)

    results, missing, recycled, truncated = run_small_cap_disposition_screening(
        date(2020, 1, 1), date(2026, 8, 26), provider=FakeProvider()
    )
    assert calls, "the production entry point must apply the recycled-ticker mask"
    assert missing == ["GONE"]
    assert isinstance(recycled, list) and isinstance(truncated, list)
    for r in results:
        assert r.deflated_sharpe.n_trials == DISPOSITION_N_TRIALS


# =====================================================================
# Entry-point guards
# =====================================================================


def test_a_start_before_membership_coverage_is_refused_loudly():
    # A formation before coverage would silently see an empty universe.
    for entry in (run_small_cap_disposition_screening, run_small_cap_ivol_screening):
        with pytest.raises(ValueError, match="predates point-in-time small-cap"):
            entry(date(2015, 1, 1), date(2026, 1, 1))


def test_ivol_entry_point_returns_all_of_its_diagnostic_lists(monkeypatch):
    import app.services.research_lab.cross_sectional_small_mid_cap as module

    close, _volume = _synthetic_panel(700, 30, seed=41)
    close.columns = [f"SC{i:03d}" for i in range(30)]
    shares = {t: pd.Series([1e8] * len(close), index=close.index) for t in close.columns}

    class FakeProvider:
        def get_price_history(self, tickers, start, end):
            return close, ["NOPRICE"]

        def get_market_cap_basis(self, tickers, start, end):
            return close, {}, []

        def get_shares_outstanding(self, tickers, start, end):
            return shares, []

    monkeypatch.setattr(module, "get_universe_over", lambda s, e: list(close.columns))
    monkeypatch.setattr(module, "was_member", lambda _t, _d: True)

    results, missing, recycled, truncated, no_shares, n_lifecycle, n_implausible = (
        run_small_cap_ivol_screening(
            date(2020, 1, 1), date(2026, 8, 26), provider=FakeProvider()
        )
    )
    assert missing == ["NOPRICE"]
    assert recycled == [] and truncated == [] and no_shares == []
    # Clean synthetic data: both cross-endpoint checks must run and refuse
    # NOTHING. A non-zero count here would mean the checks are deleting good
    # data across the whole universe, which is the failure mode that matters
    # far more than a missed splice.
    assert n_lifecycle == 0 and n_implausible == 0
    assert results
    for r in results:
        assert r.deflated_sharpe.n_trials == IVOL_N_TRIALS == 42
        # The family's defining property survives the re-run: legs are
        # value-weighted, so the fallback tally is populated rather than 0.
        assert r.n_value_weighted_legs > 0


# =====================================================================
# Section 7: cross-endpoint contamination. The price endpoint and the
# shares-outstanding endpoint are joined by ticker symbol alone, and a
# ticker symbol is not a company. Confirmed live 2026-08-27 on this
# module's own production universe: 3,383 share-count observations across
# 16 of 849 priced tickers are dated outside their ticker's price history.
# =====================================================================


def test_the_ivol_entry_point_applies_both_cross_endpoint_checks(monkeypatch):
    """AMR in miniature, end to end: a share-count history that begins years
    before this symbol had any price at all belongs to whoever held the
    symbol then. The real case is Alta Mesa Resources' 176M-527M share
    counts (from 2018-11-28) sitting in front of Alpha Metallurgical
    Resources' prices (from 2021-02-08, real count 12.7M-21.7M), a
    0.0476x step with no split anywhere near it.

    This is the test that would fail if the wiring were removed — the whole
    reason the two counts are returned rather than logged."""
    import app.services.research_lab.cross_sectional_small_mid_cap as module

    close, _volume = _synthetic_panel(700, 30, seed=41)
    close.columns = [f"SC{i:03d}" for i in range(30)]
    # One ticker has no price for the first 400 rows — the successor
    # company's listing date, in the register the real gaps live in (the
    # smallest measured here is 23 days, the largest 2,795).
    close.iloc[:400, 0] = np.nan
    contaminated = close.columns[0]

    shares = {t: pd.Series([1e8] * len(close), index=close.index) for t in close.columns}
    # ... and a share history that runs the WHOLE window, including the 400
    # rows on which this symbol belonged to somebody else.
    shares[contaminated] = pd.Series([5.0e8] * len(close), index=close.index)

    class FakeProvider:
        def get_price_history(self, tickers, start, end):
            return close, []

        def get_market_cap_basis(self, tickers, start, end):
            return close, {}, []

        def get_shares_outstanding(self, tickers, start, end):
            return shares, []

    monkeypatch.setattr(module, "get_universe_over", lambda s, e: list(close.columns))
    monkeypatch.setattr(module, "was_member", lambda _t, _d: True)

    _results, _missing, _recycled, _truncated, _no_shares, n_lifecycle, _n_implausible = (
        run_small_cap_ivol_screening(
            date(2020, 1, 1), date(2026, 8, 26), provider=FakeProvider()
        )
    )
    # 400 rows minus whatever the 10-day grace window admits.
    assert n_lifecycle > 0, "the entry point must apply the lifecycle check"
    assert n_lifecycle >= 390


def test_the_ivol_entry_point_refuses_an_implausible_market_cap(monkeypatch):
    """BNED/CRC in miniature: price and share series that overlap in time
    perfectly well and still cannot describe the same company, which only
    their PRODUCT gives away. The real floor cases are reverse-split
    back-adjustments the share series shows no matching jump for (EGRX, MARA,
    CLSK, LESL, RGS) and CRC's single corrupt 51,037-share filing on
    2020-10-30 against a real ~49M."""
    import app.services.research_lab.cross_sectional_small_mid_cap as module

    close, _volume = _synthetic_panel(700, 30, seed=43)
    close.columns = [f"SC{i:03d}" for i in range(30)]
    shares = {t: pd.Series([1e8] * len(close), index=close.index) for t in close.columns}
    # A count 1/1000th of the real one — CRC's defect, which leaves the
    # dates overlapping perfectly and only shows up in price x shares.
    shares[close.columns[0]] = pd.Series([1e4] * len(close), index=close.index)

    class FakeProvider:
        def get_price_history(self, tickers, start, end):
            return close, []

        def get_market_cap_basis(self, tickers, start, end):
            return close, {}, []

        def get_shares_outstanding(self, tickers, start, end):
            return shares, []

    monkeypatch.setattr(module, "get_universe_over", lambda s, e: list(close.columns))
    monkeypatch.setattr(module, "was_member", lambda _t, _d: True)

    *_rest, n_lifecycle, n_implausible = run_small_cap_ivol_screening(
        date(2020, 1, 1), date(2026, 8, 26), provider=FakeProvider()
    )
    # The dates line up exactly, so the TIME axis structurally cannot see
    # this one — that is precisely why there are two checks.
    assert n_lifecycle == 0
    assert n_implausible > 0


def test_the_small_cap_band_is_not_the_sp500_band(monkeypatch):
    """Reusing cross_sectional_ivol's own [$1bn, $6T] defaults here would
    delete a quarter of this universe's real data: measured on the real
    production run, that floor alone refuses 199,765 of 825,668 eligible
    cells (24.19%), because a real S&P 600 market cap has a 25th percentile
    of $1.02bn and a median of only $1.73bn. The band must be this module's
    own."""
    assert SMALL_CAP_MIN_PLAUSIBLE_MARKET_CAP_USD < SP500_MIN_PLAUSIBLE_MARKET_CAP_USD
    assert SMALL_CAP_MAX_PLAUSIBLE_MARKET_CAP_USD < SP500_MAX_PLAUSIBLE_MARKET_CAP_USD

    # The real distribution's measured landmarks must all sit INSIDE the
    # band — p0.1 $0.118bn, p1 $0.267bn, median $1.73bn, p99.9 $34.97bn,
    # plus the two extremes the margins were set against: TETRA at $28.9M
    # (the smallest real eligible reading, 2020 COVID trough) and SanDisk
    # at $345.8bn (the largest reading anywhere in the priced frame).
    real = pd.DataFrame(
        {"A": [2.89e7, 1.18e8, 2.67e8, 1.73e9, 3.497e10, 6.19e10, 3.458e11]}
    )
    mask = implausible_market_cap_mask(
        real,
        minimum_usd=SMALL_CAP_MIN_PLAUSIBLE_MARKET_CAP_USD,
        maximum_usd=SMALL_CAP_MAX_PLAUSIBLE_MARKET_CAP_USD,
    )
    assert not mask["A"].any()

    # The S&P 500 band would refuse the bottom three of those seven — every
    # landmark at or below this universe's 1st percentile, including the one
    # a quarter of its real cells sit near.
    sp500 = implausible_market_cap_mask(real)
    assert int(sp500["A"].sum()) == 3
    assert bool(sp500["A"].iloc[2])  # p1 = $0.267bn, refused by the S&P 500 floor


def test_the_disposition_family_cannot_be_touched_by_the_share_count_fix(monkeypatch):
    """The 12 disposition specs need no before/after because they cannot
    have one: this entry point never asks for a share count. Pinned as a
    property of the code path, not measured — a provider whose
    get_shares_outstanding raises must still produce a full screening."""
    import app.services.research_lab.cross_sectional_small_mid_cap as module

    close, volume = _synthetic_panel(900, 30, seed=47)
    close.columns = volume.columns = [f"SC{i:03d}" for i in range(30)]
    open_ = close.copy()

    class NoSharesProvider:
        def get_daily_ohlcv(self, tickers, start, end):
            return {"close": close, "open": open_, "volume": volume}, []

        def get_shares_outstanding(self, tickers, start, end):  # pragma: no cover
            raise AssertionError(
                "the disposition family must never reach the shares-outstanding endpoint"
            )

        def get_market_cap_basis(self, tickers, start, end):  # pragma: no cover
            raise AssertionError("the disposition family must never build a market cap")

    monkeypatch.setattr(module, "get_universe_over", lambda s, e: list(close.columns))
    monkeypatch.setattr(module, "was_member", lambda _t, _d: True)

    results, _missing, _recycled, _truncated = run_small_cap_disposition_screening(
        date(2020, 1, 1), date(2026, 8, 26), provider=NoSharesProvider()
    )
    # It completed — the AssertionError guards above were never reached, which
    # is the whole claim. (Not every spec clears this short panel's warmup;
    # that is the harness's own data floor, unrelated to share counts.)
    assert results
    # And no spec in the family can even ask for one.
    for spec in SMALL_CAP_DISPOSITION_FAMILY:
        assert not spec.requires_market_cap
        assert spec.leg_weighting == "magnitude"


def test_the_two_checks_are_reused_from_the_module_that_owns_them():
    """Not reimplemented — the same objects cross_sectional_ivol.py exports
    and run_round_d1_screening / run_buyback_screening apply. A second
    implementation would make 'the small-cap rate differs from the large-cap
    rate' an artifact of the second implementation, which is the same
    argument this module's docstring makes for importing the SIGNALS."""
    import app.services.research_lab.cross_sectional_ivol as owner
    import app.services.research_lab.cross_sectional_small_mid_cap as module

    assert module.restrict_share_counts_to_price_lifecycle is (
        owner.restrict_share_counts_to_price_lifecycle
    )
    assert module.implausible_market_cap_mask is owner.implausible_market_cap_mask


def test_the_real_amr_contamination_shape_is_refused():
    """The confirmed 2026-08-27 case, at its real magnitudes: Alta Mesa
    Resources' 384,351,008-share filing dated inside a window where the AMR
    symbol carried no price at all, against Alpha Metallurgical Resources'
    18,308,800. Kept as a data-shaped regression test so a future change to
    the grace window or the lifecycle bounds cannot quietly re-admit it."""
    idx = pd.bdate_range("2018-11-28", periods=800)
    close = pd.DataFrame({"AMR": [np.nan] * 560 + [70.0] * 240}, index=idx)
    shares = pd.Series(
        [175_956_992.0, 384_351_008.0, 18_308_800.0],
        index=[idx[0], idx[400], idx[555]],  # the third is 5 business days early
    )

    restricted, dropped = restrict_share_counts_to_price_lifecycle({"AMR": shares}, close)

    assert dropped == {"AMR": 2}
    # Only the successor's own count survives — and it does survive, because
    # a real filing landing just before the first price bar is exactly what
    # the grace window exists to keep (AMR's real one is 3 days early).
    assert list(restricted["AMR"]) == [18_308_800.0]
