"""Tests for the short-interest long-side family
(cross_sectional_short_interest.py).

Mirrors test_cross_sectional_asset_growth.py's structure: family-shape
assertions against the pre-declared grid, hand-computed panel arithmetic,
the point-in-time publication bound, the split guard that is load-bearing
for THIS factor specifically, the common-cross-section mask that makes the
two normalizer halves comparable, both signals' direction and refusal
contracts, and harness integration including structural look-ahead
impossibility.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.services.market_data.finra_short_interest_provider import (
    PUBLICATION_LAG_CALENDAR_DAYS,
    ShortInterestObservation,
    publication_date,
)
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    fixed_universe_membership,
    run_cross_sectional_backtest,
)
from app.services.research_lab.cross_sectional_short_interest import (
    SHORT_INTEREST_FAMILY,
    SHORT_INTEREST_FAMILY_KEY,
    SHORT_INTEREST_HOLDING_DAYS,
    SHORT_INTEREST_MAX_STALENESS_DAYS,
    SHORT_INTEREST_N_TRIALS,
    SHORT_INTEREST_NORMALIZERS,
    SHORT_INTEREST_PORTFOLIOS,
    SHORT_INTEREST_RANK_FRACTION,
    build_short_interest_family,
    build_short_interest_panels,
    measure_january_split,
    signal_low_days_to_cover,
    signal_low_short_interest_ratio,
    specs_for_normalizer,
)

# --- fixture helpers ---------------------------------------------------------


def bdays(start: str, periods: int) -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=periods)


def close_frame(index: pd.DatetimeIndex, tickers: list[str]) -> pd.DataFrame:
    return pd.DataFrame(100.0, index=index, columns=tickers)


def observation(
    settlement: str,
    short: float,
    volume: float,
    *,
    symbol: str = "AAA",
    split: bool = False,
) -> ShortInterestObservation:
    settled = date.fromisoformat(settlement)
    return ShortInterestObservation(
        symbol=symbol,
        settlement_date=settled,
        available=publication_date(settled),
        short_shares=short,
        average_daily_volume=volume,
        market_class="NYSE",
        split_flagged=split,
    )


def share_frame(index: pd.DatetimeIndex, tickers: list[str], value: float | dict) -> pd.DataFrame:
    if isinstance(value, dict):
        return pd.DataFrame({t: float(value.get(t, np.nan)) for t in tickers}, index=index)
    return pd.DataFrame(float(value), index=index, columns=tickers)


# --- the pre-declared grid ---------------------------------------------------


def test_family_is_exactly_twelve_definitions_matching_the_declared_grid():
    specs = build_short_interest_family()
    assert len(specs) == SHORT_INTEREST_N_TRIALS == 12
    assert (
        len(SHORT_INTEREST_NORMALIZERS)
        * len(SHORT_INTEREST_HOLDING_DAYS)
        * len(SHORT_INTEREST_PORTFOLIOS)
        == 12
    )


def test_family_covers_every_axis_combination_exactly_once():
    seen = {
        (spec.pattern_id.split("_")[1], spec.portfolio, spec.holding_days)
        for spec in build_short_interest_family()
    }
    assert len(seen) == 12


def test_both_portfolios_appear_in_equal_number_so_neither_half_dominates():
    specs = build_short_interest_family()
    counts = {p: sum(1 for s in specs if s.portfolio == p) for p in SHORT_INTEREST_PORTFOLIOS}
    assert counts == {"long_universe_hedged": 6, "long_short": 6}


def test_the_long_side_portfolio_is_present_because_it_is_the_candidate():
    """The candidate is specifically BHJ's LONG-side reading, which only
    long_universe_hedged can express (a long_short spread cannot separate a
    long-leg effect from the long-known heavily-shorted one)."""
    assert "long_universe_hedged" in SHORT_INTEREST_PORTFOLIOS
    assert any(s.portfolio == "long_universe_hedged" for s in build_short_interest_family())


def test_rank_fraction_is_fixed_at_the_papers_fifth_percentile_and_never_searched():
    specs = build_short_interest_family()
    assert SHORT_INTEREST_RANK_FRACTION == 0.05
    assert {s.rank_fraction for s in specs} == {0.05}


def test_a_monthly_hold_is_deliberately_included_here_unlike_the_edgar_families():
    """The ranking variable refreshes twice a month, so a 21-day hold trades
    on real new information — the opposite of the annual-fundamental
    families, which exclude 21 for exactly that reason."""
    assert 21 in SHORT_INTEREST_HOLDING_DAYS


def test_pattern_ids_are_unique_and_every_spec_carries_the_real_citation():
    specs = build_short_interest_family()
    assert len({s.pattern_id for s in specs}) == len(specs)
    for spec in specs:
        assert "Boehmer" in spec.citation
        assert "96(1), 2010" in spec.citation
        assert spec.family == SHORT_INTEREST_FAMILY


def test_the_citation_discloses_that_the_full_text_could_not_be_obtained():
    """A citation that read like a clean replication would overstate what
    this build could verify. The disclosure belongs on the persisted row,
    not only in the module docstring."""
    citation = build_short_interest_family()[0].citation
    assert "could not be obtained" in citation
    assert "second-hand" in citation


def test_family_key_is_distinct_from_every_sibling_family():
    from app.services.research_lab.cross_sectional_asset_growth import ASSET_GROWTH_FAMILY_KEY

    assert SHORT_INTEREST_FAMILY_KEY == "short_interest"
    assert SHORT_INTEREST_FAMILY_KEY != ASSET_GROWTH_FAMILY_KEY


def test_specs_for_normalizer_partitions_the_family_exactly():
    ratio = specs_for_normalizer("short_interest_ratio")
    dtc = specs_for_normalizer("days_to_cover")
    assert len(ratio) == len(dtc) == 6
    assert {s.pattern_id for s in ratio}.isdisjoint({s.pattern_id for s in dtc})
    assert {s.pattern_id for s in ratio + dtc} == {
        s.pattern_id for s in build_short_interest_family()
    }


def test_specs_for_normalizer_rejects_an_unknown_name():
    with pytest.raises(ValueError, match="unknown normalizer"):
        specs_for_normalizer("turnover")


# --- panel arithmetic --------------------------------------------------------


def test_both_normalizers_match_their_hand_computed_values():
    index = bdays("2026-01-01", 60)
    close = close_frame(index, ["AAA"])
    ratio, dtc, _diag = build_short_interest_panels(
        close,
        {"AAA": [observation("2026-01-15", short=2_000.0, volume=500.0)]},
        share_frame(index, ["AAA"], 100_000.0),
    )
    visible = pd.Timestamp(publication_date(date(2026, 1, 15)))
    on = index[index.searchsorted(visible, side="left")]
    assert ratio.at[on, "AAA"] == pytest.approx(2_000.0 / 100_000.0)  # 2% of shares out
    assert dtc.at[on, "AAA"] == pytest.approx(2_000.0 / 500.0)  # 4 days to cover


def test_a_value_is_invisible_before_its_publication_date_and_visible_after():
    """THE point-in-time contract. A settlement-dated value must not appear
    on the settlement date — FINRA had not published it yet."""
    index = bdays("2026-01-01", 60)
    close = close_frame(index, ["AAA"])
    ratio, _dtc, _diag = build_short_interest_panels(
        close,
        {"AAA": [observation("2026-01-15", short=1_000.0, volume=100.0)]},
        share_frame(index, ["AAA"], 10_000.0),
    )
    settlement = pd.Timestamp("2026-01-15")
    available = pd.Timestamp(publication_date(date(2026, 1, 15)))
    assert available > settlement
    before = ratio.loc[ratio.index < available, "AAA"]
    assert before.isna().all()
    after = ratio.loc[ratio.index >= available, "AAA"].dropna()
    assert len(after) > 0
    assert after.to_numpy() == pytest.approx(0.1)


def test_the_publication_bound_used_here_is_the_providers_not_a_local_copy():
    assert publication_date(date(2026, 1, 15)) == date(2026, 1, 15) + timedelta(
        days=PUBLICATION_LAG_CALENDAR_DAYS
    )


def test_a_split_flagged_cycle_is_refused_and_counted():
    """LOAD-BEARING FOR THIS FACTOR. FINRA's short shares are raw as of the
    settlement date; the SEC share count is raw as of a cover date up to a
    quarter earlier. A split between them corrupts the ratio by the split
    factor, and a 2:1 split HALVES it — pushing the name straight into the
    low-short-interest long leg this family is testing."""
    index = bdays("2026-01-01", 60)
    close = close_frame(index, ["AAA"])
    ratio, dtc, diag = build_short_interest_panels(
        close,
        {"AAA": [observation("2026-01-15", short=1_000.0, volume=100.0, split=True)]},
        share_frame(index, ["AAA"], 10_000.0),
    )
    assert diag.n_refused.get("stock_split_cycle") == 1
    assert ratio["AAA"].isna().all()
    assert dtc["AAA"].isna().all()


def test_a_ticker_with_no_share_count_is_refused_from_the_ratio_and_counted():
    index = bdays("2026-01-01", 60)
    close = close_frame(index, ["AAA"])
    ratio, _dtc, diag = build_short_interest_panels(
        close,
        {"AAA": [observation("2026-01-15", short=1_000.0, volume=100.0)]},
        share_frame(index, ["AAA"], {"AAA": np.nan}),
    )
    assert diag.n_refused.get("no_share_count") == 1
    assert ratio["AAA"].isna().all()


def test_a_non_positive_share_count_is_refused_rather_than_producing_an_infinity():
    index = bdays("2026-01-01", 60)
    close = close_frame(index, ["AAA"])
    ratio, _dtc, diag = build_short_interest_panels(
        close,
        {"AAA": [observation("2026-01-15", short=1_000.0, volume=100.0)]},
        share_frame(index, ["AAA"], 0.0),
    )
    assert diag.n_refused.get("non_positive_share_count") == 1
    assert ratio["AAA"].isna().all()


# --- the common-cross-section mask -------------------------------------------


def test_the_mask_makes_both_panels_finite_in_exactly_the_same_cells():
    """Without this, the two halves of the grid would rank different
    universes and the normalizer axis would measure a universe difference
    rather than the normalizer (module docstring section 3)."""
    index = bdays("2026-01-01", 60)
    close = close_frame(index, ["AAA", "BBB"])
    ratio, dtc, _diag = build_short_interest_panels(
        close,
        {
            "AAA": [observation("2026-01-15", short=1_000.0, volume=100.0, symbol="AAA")],
            # BBB has short interest but no share count -> no ratio, so its
            # days-to-cover must be masked away too.
            "BBB": [observation("2026-01-15", short=2_000.0, volume=100.0, symbol="BBB")],
        },
        share_frame(index, ["AAA", "BBB"], {"AAA": 10_000.0, "BBB": np.nan}),
    )
    assert np.array_equal(
        np.isfinite(ratio.to_numpy()), np.isfinite(dtc.to_numpy())
    ), "the two panels must be finite in exactly the same cells"
    assert dtc["BBB"].isna().all()
    assert dtc["AAA"].notna().any()


def test_the_mask_records_how_much_each_panel_lost():
    index = bdays("2026-01-01", 60)
    close = close_frame(index, ["AAA", "BBB"])
    _ratio, _dtc, diag = build_short_interest_panels(
        close,
        {
            "AAA": [observation("2026-01-15", short=1_000.0, volume=100.0, symbol="AAA")],
            "BBB": [observation("2026-01-15", short=2_000.0, volume=100.0, symbol="BBB")],
        },
        share_frame(index, ["AAA", "BBB"], {"AAA": 10_000.0, "BBB": np.nan}),
    )
    # BBB's days-to-cover cells existed and were removed by the mask.
    assert diag.n_cells_dtc_only > 0
    assert diag.n_cells_common > 0
    assert diag.tickers_never_ranked == ["BBB"]


# --- the step function and staleness -----------------------------------------


def test_a_value_is_carried_forward_as_a_step_never_interpolated():
    index = bdays("2026-01-01", 90)
    close = close_frame(index, ["AAA"])
    ratio, _dtc, _diag = build_short_interest_panels(
        close,
        {
            "AAA": [
                observation("2026-01-15", short=1_000.0, volume=100.0),
                observation("2026-01-30", short=3_000.0, volume=100.0),
            ]
        },
        share_frame(index, ["AAA"], 10_000.0),
    )
    values = sorted(set(ratio["AAA"].dropna().round(10)))
    assert values == [pytest.approx(0.1), pytest.approx(0.3)], (
        "only the two filed levels may appear — an interpolated panel would "
        "carry intermediate values that were never published"
    )


def test_a_value_carried_past_the_staleness_bound_is_refused():
    """Cycles are ~15 days apart, so a value older than 45 days means three
    consecutive missed cycles — disappearance (delisting, ticker change),
    not staleness. A dead name must stop ranking."""
    index = bdays("2026-01-01", 200)
    close = close_frame(index, ["AAA"])
    ratio, _dtc, _diag = build_short_interest_panels(
        close,
        {"AAA": [observation("2026-01-15", short=1_000.0, volume=100.0)]},
        share_frame(index, ["AAA"], 10_000.0),
    )
    available = pd.Timestamp(publication_date(date(2026, 1, 15)))
    cutoff = available + pd.Timedelta(days=SHORT_INTEREST_MAX_STALENESS_DAYS)
    assert ratio.loc[ratio.index <= cutoff, "AAA"].notna().any()
    assert ratio.loc[ratio.index > cutoff, "AAA"].isna().all()


def test_the_panel_is_never_back_filled_before_the_first_observation():
    index = bdays("2026-01-01", 60)
    close = close_frame(index, ["AAA"])
    ratio, _dtc, _diag = build_short_interest_panels(
        close,
        {"AAA": [observation("2026-01-30", short=1_000.0, volume=100.0)]},
        share_frame(index, ["AAA"], 10_000.0),
    )
    first_visible = pd.Timestamp(publication_date(date(2026, 1, 30)))
    assert ratio.loc[ratio.index < first_visible, "AAA"].isna().all()


def test_panels_are_aligned_to_close_exactly():
    index = bdays("2026-01-01", 40)
    close = close_frame(index, ["AAA", "BBB"])
    ratio, dtc, _diag = build_short_interest_panels(close, {}, share_frame(index, ["AAA", "BBB"], 1.0))
    for frame in (ratio, dtc):
        assert frame.index.equals(close.index)
        assert frame.columns.equals(close.columns)


# --- the two signals ---------------------------------------------------------


@pytest.mark.parametrize(
    "signal_fn", [signal_low_short_interest_ratio, signal_low_days_to_cover]
)
def test_both_signals_rank_the_least_shorted_name_on_top(signal_fn):
    """The harness's convention is top-is-long, and this family's long leg
    must be the LOW-short-interest side — the paper's documented
    direction."""
    index = bdays("2026-01-01", 3)
    frame = pd.DataFrame(
        {"LOW": [0.01, 0.01, 0.01], "MID": [0.05, 0.05, 0.05], "HIGH": [0.20, 0.20, 0.20]},
        index=index,
    )
    signal = signal_fn(
        CrossSectionalData(close=close_frame(index, list(frame.columns)), fundamental_signal=frame)
    )
    assert signal.idxmax() == "LOW"
    assert signal.idxmin() == "HIGH"


@pytest.mark.parametrize(
    "signal_fn", [signal_low_short_interest_ratio, signal_low_days_to_cover]
)
def test_both_signals_refuse_a_ticker_with_no_current_value(signal_fn):
    index = bdays("2026-01-01", 3)
    frame = pd.DataFrame({"AAA": [0.01, 0.01, 0.01], "BBB": [0.02, 0.02, np.nan]}, index=index)
    signal = signal_fn(
        CrossSectionalData(close=close_frame(index, list(frame.columns)), fundamental_signal=frame)
    )
    assert np.isfinite(signal["AAA"])
    assert np.isnan(signal["BBB"])


@pytest.mark.parametrize(
    "signal_fn", [signal_low_short_interest_ratio, signal_low_days_to_cover]
)
def test_both_signals_raise_loudly_when_the_fundamental_frame_is_absent(signal_fn):
    index = bdays("2026-01-01", 3)
    with pytest.raises(ValueError, match="requires_fundamental_signal"):
        signal_fn(CrossSectionalData(close=close_frame(index, ["AAA"])))


# --- harness integration -----------------------------------------------------


def test_the_frame_is_sliced_to_the_formation_date_so_look_ahead_is_impossible():
    """The structural guarantee: a signal function CANNOT read a future row,
    however buggy, because the row is not in the frame it is handed."""
    index = bdays("2024-01-01", 120)
    tickers = [f"T{i}" for i in range(20)]
    close = pd.DataFrame(
        np.linspace(100.0, 150.0, len(index))[:, None] * np.ones(len(tickers)),
        index=index,
        columns=tickers,
    )
    panel = pd.DataFrame(
        np.tile(np.linspace(0.01, 0.2, len(tickers)), (len(index), 1)),
        index=index,
        columns=tickers,
    )
    seen_last_rows: list[pd.Timestamp] = []

    def recording_signal(history: CrossSectionalData) -> pd.Series:
        seen_last_rows.append(history.fundamental_signal.index[-1])
        return signal_low_short_interest_ratio(history)

    spec = CrossSectionalSpec(
        pattern_id="probe",
        family=SHORT_INTEREST_FAMILY,
        citation="probe",
        signal_fn=recording_signal,
        lookback_days=1,
        holding_days=21,
        portfolio="long_short",
        rank_fraction=SHORT_INTEREST_RANK_FRACTION,
        requires_fundamental_signal=True,
    )
    config = CrossSectionalConfig(formation_start=index[5].date(), min_names_per_leg=1)
    result = run_cross_sectional_backtest(
        CrossSectionalData(close=close, fundamental_signal=panel),
        spec,
        config,
        fixed_universe_membership(tickers),
    )
    formation_dates = [f.date for f in result.formations]
    assert seen_last_rows == formation_dates


def test_a_spec_requiring_the_fundamental_frame_fails_loudly_when_it_is_absent():
    index = bdays("2024-01-01", 60)
    tickers = [f"T{i}" for i in range(20)]
    close = pd.DataFrame(100.0, index=index, columns=tickers)
    spec = build_short_interest_family()[0]
    with pytest.raises(ValueError):
        run_cross_sectional_backtest(
            CrossSectionalData(close=close),
            spec,
            CrossSectionalConfig(formation_start=index[2].date()),
            fixed_universe_membership(tickers),
        )


# --- the pre-declared January diagnostic -------------------------------------


def test_january_split_separates_january_from_the_rest():
    index = pd.to_datetime(["2024-01-05", "2024-01-12", "2024-03-05", "2024-03-12"])
    returns = pd.Series([0.02, 0.04, 0.001, 0.003], index=index)
    january, other = measure_january_split(returns)
    assert january == pytest.approx(0.03)
    assert other == pytest.approx(0.002)


def test_january_split_is_nan_when_a_side_has_no_observations():
    index = pd.to_datetime(["2024-03-05", "2024-03-12"])
    january, other = measure_january_split(pd.Series([0.001, 0.003], index=index))
    assert np.isnan(january)
    assert other == pytest.approx(0.002)
