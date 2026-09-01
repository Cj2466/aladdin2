"""Tests for the asset growth / investment-effect family
(cross_sectional_asset_growth.py).

Mirrors test_cross_sectional_quality.py's structure: family-shape
assertions against the pre-declared grid, companyfacts-shaped synthetic
fixtures for the factor builder, hand-computed formula checks, the
entity-discontinuity guard that is load-bearing for THIS factor
specifically, both signals' direction and refusal contracts, the
pre-declared median (not mean) industry centering, and harness
integration including structural look-ahead impossibility.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.market_data.edgar_xbrl_provider import extract_line_items
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    fixed_universe_membership,
    run_cross_sectional_backtest,
)
from app.services.research_lab.cross_sectional_asset_growth import (
    ASSET_GROWTH_CONDITIONINGS,
    ASSET_GROWTH_FAMILY,
    ASSET_GROWTH_FAMILY_KEY,
    ASSET_GROWTH_HOLDING_DAYS,
    ASSET_GROWTH_N_TRIALS,
    ASSET_GROWTH_RANK_FRACTIONS,
    build_asset_growth_family,
    compute_asset_growth_observations,
    signal_low_asset_growth,
    signal_low_asset_growth_industry_neutral,
)
from app.services.research_lab.cross_sectional_quality import (
    QUALITY_RANK_FRACTION,
    QUALITY_ROBUSTNESS_RANK_FRACTION,
    build_point_in_time_factor_frame,
)
from app.services.research_lab.cross_sectional_quality_neutral import MIN_BUCKET_SIZE

# --- fixture helpers (companyfacts-shaped, per the real nesting) ------------


def instant(end: str, val: float, filed: str, form: str = "10-K") -> dict:
    return {"end": end, "val": val, "filed": filed, "form": form}


def assets_facts(entries: list[dict]) -> dict:
    """A minimal companyfacts document carrying only total assets — which is
    genuinely all this factor needs (module docstring section 3)."""
    return {
        "cik": 999,
        "entityName": "Synthetic Corp",
        "facts": {"us-gaap": {"Assets": {"label": "Assets", "units": {"USD": entries}}}},
    }


def growth_of(entries: list[dict]):
    return compute_asset_growth_observations(extract_line_items(assets_facts(entries)))


def bdays(start: str, periods: int) -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=periods)


def growth_view(values: dict[str, float]) -> CrossSectionalData:
    """A history view whose LAST row carries the given raw growth rates —
    the shape the harness hands a signal function at a formation."""
    index = bdays("2024-01-02", 5)
    close = pd.DataFrame(100.0, index=index, columns=list(values))
    frame = pd.DataFrame(np.nan, index=index, columns=list(values))
    frame.iloc[-1] = pd.Series(values)
    return CrossSectionalData(close=close, fundamental_signal=frame)


def bucket_frame_for(view: CrossSectionalData, buckets: dict[str, str]) -> pd.DataFrame:
    frame = view.fundamental_signal
    assert frame is not None
    return pd.DataFrame(
        [[buckets.get(t) for t in frame.columns]] * len(frame.index),
        index=frame.index,
        columns=frame.columns,
        dtype=object,
    )


# --- the pre-declared family shape ------------------------------------------


def test_family_is_exactly_twelve_definitions_matching_the_declared_grid():
    specs = build_asset_growth_family(pd.DataFrame())
    assert len(specs) == ASSET_GROWTH_N_TRIALS == 12
    assert ASSET_GROWTH_N_TRIALS == (
        len(ASSET_GROWTH_CONDITIONINGS)
        * len(ASSET_GROWTH_HOLDING_DAYS)
        * len(ASSET_GROWTH_RANK_FRACTIONS)
    )


def test_family_covers_every_axis_combination_exactly_once():
    specs = build_asset_growth_family(pd.DataFrame())
    seen = {(s.pattern_id.startswith("ag_neutral"), s.holding_days, s.rank_fraction) for s in specs}
    expected = {
        (neutral, hold, frac)
        for neutral in (False, True)
        for hold in ASSET_GROWTH_HOLDING_DAYS
        for frac in (QUALITY_RANK_FRACTION, QUALITY_ROBUSTNESS_RANK_FRACTION)
    }
    assert seen == expected
    assert len(seen) == len(specs)  # exactly once each, no duplicates


def test_both_conditionings_are_present_in_equal_number():
    specs = build_asset_growth_family(pd.DataFrame())
    raw = [s for s in specs if s.pattern_id.startswith("ag_low")]
    neutral = [s for s in specs if s.pattern_id.startswith("ag_neutral")]
    # The load-bearing design property (docstring section 4): the sector
    # confound test is HALF THE GRID, not a follow-up study.
    assert len(raw) == len(neutral) == 6


def test_pattern_ids_are_unique_and_every_spec_carries_the_real_citation():
    specs = build_asset_growth_family(pd.DataFrame())
    assert len({s.pattern_id for s in specs}) == len(specs)
    for spec in specs:
        assert spec.family == ASSET_GROWTH_FAMILY
        assert spec.requires_fundamental_signal
        assert "Cooper, Gulen & Schill" in spec.citation
        assert "1609-1651" in spec.citation


def test_family_key_is_distinct_from_the_sibling_quality_families():
    assert ASSET_GROWTH_FAMILY_KEY == "asset_growth"
    assert ASSET_GROWTH_FAMILY_KEY not in {"quality_cbop", "quality_noa"}


def test_grid_is_long_short_throughout_and_excludes_monthly_holds():
    specs = build_asset_growth_family(pd.DataFrame())
    # long_universe_hedged is deliberately absent — hedging against the
    # sector-imbalanced universe would reintroduce the exposure the neutral
    # conditioning removes (docstring section 4).
    assert all(s.portfolio == "long_short" for s in specs)
    assert all(s.leg_weighting == "magnitude" for s in specs)
    assert all(s.cohort_formation_days is None for s in specs)
    assert 21 not in ASSET_GROWTH_HOLDING_DAYS


# --- the factor formula -----------------------------------------------------


def test_asset_growth_matches_the_hand_computed_value():
    obs, diag = growth_of(
        [
            instant("2022-12-31", 2000.0, "2023-02-10"),
            instant("2023-12-31", 2500.0, "2024-02-15"),
        ]
    )
    assert len(obs) == 1
    # (2500 - 2000) / 2000 = +0.25, returned UNNEGATED (the raw economic
    # quantity); the direction flip lives in the signal functions.
    assert obs[0].value == pytest.approx(0.25)
    assert obs[0].end == date(2023, 12, 31)
    assert diag.n_observations == 1
    assert not diag.n_refused


def test_asset_growth_is_negative_when_the_balance_sheet_shrinks():
    obs, _ = growth_of(
        [
            instant("2022-12-31", 1000.0, "2023-02-10"),
            instant("2023-12-31", 750.0, "2024-02-15"),
        ]
    )
    assert obs[0].value == pytest.approx(-0.25)


def test_value_becomes_public_at_the_latest_filing_used_never_the_period_end():
    obs, _ = growth_of(
        [
            instant("2022-12-31", 2000.0, "2023-02-10"),
            instant("2023-12-31", 2500.0, "2024-02-15"),
        ]
    )
    # Not 2023-12-31 (the fiscal period end, which precedes public
    # availability by the whole filing lag) — the later of the two filings.
    assert obs[0].available == date(2024, 2, 15)


def test_a_non_positive_lagged_asset_base_is_refused_and_counted():
    obs, diag = growth_of(
        [
            instant("2022-12-31", 0.0, "2023-02-10"),
            instant("2023-12-31", 2500.0, "2024-02-15"),
        ]
    )
    assert obs == []
    assert diag.n_refused["non_positive_lagged_assets"] == 1


def test_a_multi_year_filing_gap_is_never_treated_as_a_one_year_change():
    """A missing 10-K must not let a two-year change masquerade as annual
    growth — _annual_pairs' 250..480-day window is what prevents it."""
    obs, _ = growth_of(
        [
            instant("2021-12-31", 1000.0, "2022-02-10"),
            instant("2023-12-31", 4000.0, "2024-02-15"),
        ]
    )
    assert obs == []


# --- THE load-bearing guard for this factor (docstring section 3) -----------


def test_a_shell_to_operating_company_transition_is_refused():
    """The single most important data guard here. TechnipFMC really filed
    total assets of $74,100 against $28.3B the next year; as an asset
    GROWTH input that is a growth rate of ~+38,000,000%, which under any
    ranking would pin the name to the short leg's extreme for a year."""
    obs, diag = growth_of(
        [
            instant("2016-12-31", 74_100.0, "2017-02-10"),
            instant("2017-12-31", 28_300_000_000.0, "2018-02-15"),
        ]
    )
    assert obs == []
    assert diag.n_refused["assets_entity_scale_break"] == 1


def test_the_guard_is_symmetric_and_catches_a_collapse_too():
    obs, diag = growth_of(
        [
            instant("2016-12-31", 28_300_000_000.0, "2017-02-10"),
            instant("2017-12-31", 74_100.0, "2018-02-15"),
        ]
    )
    assert obs == []
    assert diag.n_refused["assets_entity_scale_break"] == 1


def test_a_genuine_large_merger_year_is_kept_not_refused():
    """CBOE's real Bats-acquisition year was an ~11x asset ratio and the
    sibling family KEPT it. Asset growth financed by acquisition is part of
    the documented effect, not noise to trim (docstring section 3)."""
    obs, diag = growth_of(
        [
            instant("2016-12-31", 1_000.0, "2017-02-10"),
            instant("2017-12-31", 11_000.0, "2018-02-15"),
        ]
    )
    assert len(obs) == 1
    assert obs[0].value == pytest.approx(10.0)  # +1000% growth, deliberately kept
    assert not diag.n_refused


# --- the raw signal ---------------------------------------------------------


def test_raw_signal_ranks_the_slowest_growing_firm_on_top():
    # LOW asset growth is the long side per Cooper/Gulen/Schill; the
    # negation lands it in the harness's top decile.
    signal = signal_low_asset_growth(
        growth_view({"AGGRESSIVE": 0.60, "MID": 0.10, "CONSERVATIVE": -0.05})
    )
    assert signal.idxmax() == "CONSERVATIVE"
    assert signal.idxmin() == "AGGRESSIVE"


def test_raw_signal_refuses_a_ticker_with_no_current_value():
    signal = signal_low_asset_growth(growth_view({"AAA": 0.2, "BBB": float("nan")}))
    assert np.isfinite(signal["AAA"])
    assert not np.isfinite(signal["BBB"])


def test_raw_signal_raises_loudly_when_the_fundamental_frame_is_absent():
    index = bdays("2024-01-02", 5)
    data = CrossSectionalData(close=pd.DataFrame(100.0, index=index, columns=["AAA"]))
    with pytest.raises(ValueError, match="fundamental_signal"):
        signal_low_asset_growth(data)


# --- the industry-neutral signal --------------------------------------------


def test_neutral_signal_ranks_on_growth_relative_to_industry_peers():
    """A firm growing fast in a fast-growing industry must rank ABOVE a
    firm growing slower in a slow-growing one — that is the whole
    hypothesis."""
    view = growth_view({"FAST_IN_FAST": 0.30, "A": 0.40, "B": 0.50, "SLOW_IN_SLOW": 0.10,
                        "C": 0.02, "D": 0.04})
    buckets = bucket_frame_for(
        view,
        {"FAST_IN_FAST": "tech", "A": "tech", "B": "tech",
         "SLOW_IN_SLOW": "reit", "C": "reit", "D": "reit"},
    )
    signal = signal_low_asset_growth_industry_neutral(view, bucket_frame=buckets)
    # tech median = 0.40 -> FAST_IN_FAST is 0.10 BELOW its peers  -> +0.10
    # reit median = 0.04 -> SLOW_IN_SLOW is 0.06 ABOVE its peers  -> -0.06
    assert signal["FAST_IN_FAST"] == pytest.approx(0.10)
    assert signal["SLOW_IN_SLOW"] == pytest.approx(-0.06)
    assert signal["FAST_IN_FAST"] > signal["SLOW_IN_SLOW"]


def test_neutral_centering_is_the_median_not_the_mean():
    """The pre-declared choice (docstring section 4), and it is
    discriminating: within ONE bucket, mean and median centering give the
    same ORDER (both subtract a constant), so the difference only shows up
    ACROSS buckets of differing skew. Asset growth is bounded below at
    -100% and unbounded above, so a bucket mean is dragged by whichever
    peer closed an acquisition that year."""
    view = growth_view(
        {"T_SKEWED": 2.00, "T1": 0.00, "T2": 0.05, "T_PROBE": 0.10,
         "R1": 0.20, "R_PROBE": 0.22, "R2": 0.24}
    )
    buckets = bucket_frame_for(
        view,
        {"T_SKEWED": "tech", "T1": "tech", "T2": "tech", "T_PROBE": "tech",
         "R1": "reit", "R_PROBE": "reit", "R2": "reit"},
    )
    signal = signal_low_asset_growth_industry_neutral(view, bucket_frame=buckets)

    # tech values {0.00, 0.05, 0.10, 2.00}: median 0.075, mean 0.5375.
    # reit values {0.20, 0.22, 0.24}: median == mean == 0.22.
    assert signal["T_PROBE"] == pytest.approx(-(0.10 - 0.075))
    assert signal["R_PROBE"] == pytest.approx(-(0.22 - 0.22))
    # Under MEDIAN centering the reit probe outranks the tech probe...
    assert signal["R_PROBE"] > signal["T_PROBE"]

    # ...whereas MEAN centering would have FLIPPED that ordering. Derived
    # from the same input the function was given, not from hard-coded
    # literals, so this half of the test cannot pass vacuously.
    raw = view.fundamental_signal.iloc[-1]  # type: ignore[union-attr]
    tech = raw[["T_SKEWED", "T1", "T2", "T_PROBE"]]
    reit = raw[["R1", "R_PROBE", "R2"]]
    mean_centered_tech_probe = -(raw["T_PROBE"] - tech.mean())
    mean_centered_reit_probe = -(raw["R_PROBE"] - reit.mean())
    assert mean_centered_tech_probe > mean_centered_reit_probe
    # The one acquisitive peer (T_SKEWED at +200%) must not be allowed to
    # redefine "normal growth" for its whole industry, which is exactly
    # what the mean lets it do and the median does not.
    assert tech.mean() > tech.median()


def test_neutral_signal_refuses_a_bucket_smaller_than_the_minimum():
    view = growth_view({"LONE": 0.10, "A": 0.20, "B": 0.30, "C": 0.40})
    buckets = bucket_frame_for(view, {"LONE": "telecom_media", "A": "tech", "B": "tech", "C": "tech"})
    signal = signal_low_asset_growth_industry_neutral(view, bucket_frame=buckets)
    # A 1-member bucket centers to exactly 0.0 — pure placement noise, so
    # it is refused rather than ranked.
    assert MIN_BUCKET_SIZE == 3
    assert not np.isfinite(signal["LONE"])
    assert np.isfinite(signal["A"])


def test_neutral_signal_refuses_a_ticker_with_no_point_in_time_bucket():
    view = growth_view({"NOBUCKET": 0.10, "A": 0.20, "B": 0.30, "C": 0.40})
    buckets = bucket_frame_for(view, {"A": "tech", "B": "tech", "C": "tech"})
    signal = signal_low_asset_growth_industry_neutral(view, bucket_frame=buckets)
    assert not np.isfinite(signal["NOBUCKET"])
    assert np.isfinite(signal["B"])


def test_neutral_signal_raises_loudly_when_the_fundamental_frame_is_absent():
    index = bdays("2024-01-02", 5)
    data = CrossSectionalData(close=pd.DataFrame(100.0, index=index, columns=["AAA"]))
    with pytest.raises(ValueError, match="fundamental_signal"):
        signal_low_asset_growth_industry_neutral(data, bucket_frame=pd.DataFrame())


# --- point-in-time panel integration ----------------------------------------


def test_panel_makes_growth_visible_at_its_filing_date_not_its_period_end():
    from app.services.research_lab.cross_sectional_asset_growth import FactorObservation

    close = pd.DataFrame(100.0, index=bdays("2024-01-02", 60), columns=["AAA"])
    frame, _, _ = build_point_in_time_factor_frame(
        close, {"AAA": [FactorObservation(date(2023, 12, 31), 0.25, date(2024, 2, 15))]}
    )
    assert not np.isfinite(frame.loc["2024-02-14", "AAA"])  # NaN before the filing
    assert frame.loc["2024-02-15", "AAA"] == 0.25
    assert frame.loc["2024-03-01", "AAA"] == 0.25  # step-forward-filled, never interpolated


# --- harness integration ----------------------------------------------------


def test_a_spec_requiring_the_fundamental_frame_fails_loudly_when_it_is_absent():
    spec = build_asset_growth_family(pd.DataFrame())[0]
    index = bdays("2024-01-02", 300)
    data = CrossSectionalData(close=pd.DataFrame(100.0, index=index, columns=["AAA", "BBB"]))
    with pytest.raises(ValueError, match="fundamental_signal"):
        run_cross_sectional_backtest(
            data, spec, CrossSectionalConfig(), fixed_universe_membership(["AAA", "BBB"])
        )


def test_the_frame_is_sliced_to_the_formation_date_so_look_ahead_is_impossible():
    """A future collapse in a ticker's asset growth must not affect an
    earlier formation's legs — the harness hands the signal only rows <=
    the formation date, whatever the full frame contains."""
    tickers = [f"T{i:02d}" for i in range(12)]
    index = bdays("2024-01-02", 40)
    rng = np.random.default_rng(7)
    close = pd.DataFrame(
        100.0 * np.cumprod(1 + rng.normal(0, 0.01, size=(len(index), 12)), axis=0),
        index=index,
        columns=tickers,
    )
    # T11 has the HIGHEST growth (so ranks short) until it collapses later.
    frame = pd.DataFrame(
        np.tile(np.arange(12, dtype=float), (len(index), 1)), index=index, columns=tickers
    )
    frame.iloc[20:, 11] = -0.99

    spec = CrossSectionalSpec(
        pattern_id="ag_lookahead_probe",
        family="test",
        citation="test",
        signal_fn=signal_low_asset_growth,
        lookback_days=1,
        holding_days=10,
        portfolio="long_short",
        rank_fraction=0.2,
        requires_fundamental_signal=True,
    )
    result = run_cross_sectional_backtest(
        CrossSectionalData(close=close, fundamental_signal=frame),
        spec,
        CrossSectionalConfig(min_names_per_leg=2),
        fixed_universe_membership(tickers),
    )
    first = result.formations[0]
    assert first.date == index[1]
    # Point-in-time, T11 is still the fastest grower -> short leg, and the
    # slowest growers are long.
    assert first.long_tickers == ["T00", "T01"]
    assert "T11" in first.short_tickers
    # ...and once the collapse is inside the history view, it ranks long.
    later = [f for f in result.formations if f.date >= index[21]]
    assert later and all(f.long_tickers[0] == "T11" for f in later)
