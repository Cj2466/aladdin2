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

# 120 tickers that were continuously S&P 500 members across 2020-2023, used by
# the production-entry-point test below because run_short_interest_screening
# applies the real point-in-time membership gate and takes no membership_fn.
STABLE_SP500_MEMBERS_FOR_FIXTURES: list[str] = [
    "A", "AAL", "AAP", "AAPL", "ABBV", "ABT", "ACN", "ADBE", "ADI", "ADM",
    "ADP", "ADSK", "AEE", "AEP", "AES", "AFL", "AIG", "AIZ", "AJG", "AKAM",
    "ALB", "ALGN", "ALK", "ALL", "ALLE", "AMAT", "AMCR", "AMD", "AME", "AMGN",
    "AMP", "AMT", "AMZN", "ANET", "ANSS", "AON", "AOS", "APA", "APD", "APH",
    "APTV", "ARE", "ATO", "AVB", "AVGO", "AVY", "AWK", "AXP", "AZO", "BA",
    "BAC", "BALL", "BAX", "BBY", "BDX", "BEN", "BIIB", "BK", "BKNG", "BKR",
    "BLK", "BMY", "BR", "BSX", "BWA", "BXP", "C", "CAG", "CAH", "CAT",
    "CB", "CBOE", "CBRE", "CCI", "CCL", "CDNS", "CDW", "CE", "CF", "CFG",
    "CHD", "CHRW", "CHTR", "CI", "CINF", "CL", "CLX", "CMA", "CMCSA", "CME",
    "CMG", "CMI", "CMS", "CNC", "CNP", "COF", "COO", "COP", "COST", "CPB",
    "CPRT", "CRM", "CSCO", "CSX", "CTAS", "CTSH", "CTVA", "CVS", "CVX", "D",
    "DAL", "DD", "DE", "DFS", "DG", "DGX", "DHI", "DHR", "DIS", "DLR",
]


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


def test_a_ratio_above_one_is_refused_as_the_tripwire_it_is():
    """DEFENCE IN DEPTH, downstream of the provider's two share-count guards.
    More shares short than exist is not a short-interest ratio. This family's
    first production run emitted a realized range of 0 .. 32,050,932 before
    the guards existed, and this is the tripwire that would have caught it."""
    index = bdays("2026-01-01", 60)
    close = close_frame(index, ["AAA"])
    ratio, dtc, diag = build_short_interest_panels(
        close,
        {"AAA": [observation("2026-01-15", short=50_000.0, volume=100.0)]},
        share_frame(index, ["AAA"], 10_000.0),  # 5x more shares short than exist
    )
    assert diag.n_refused.get("implausible_ratio") == 1
    assert ratio["AAA"].isna().all()
    assert dtc["AAA"].isna().all()


def test_a_ratio_at_a_realistic_high_short_interest_level_is_kept():
    """The guard must not clip real data: 30% of shares outstanding short is
    high but entirely real, and belongs in the short leg."""
    index = bdays("2026-01-01", 60)
    close = close_frame(index, ["AAA"])
    ratio, _dtc, diag = build_short_interest_panels(
        close,
        {"AAA": [observation("2026-01-15", short=3_000.0, volume=100.0)]},
        share_frame(index, ["AAA"], 10_000.0),
    )
    assert diag.n_refused.get("implausible_ratio") is None
    assert ratio["AAA"].dropna().to_numpy() == pytest.approx(0.3)


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


# --- pinning tests added by independent verification (2026-09-02) ------------
#
# Mutation testing found several behaviours this family documents as
# load-bearing that the suite did not actually pin — including a genuine
# look-ahead and the DSR denominator that decides this family's verdict. Each
# test below was proven by reverting the behaviour it covers, confirming it
# fails, and reapplying.


def test_the_panel_is_never_back_filled_BETWEEN_two_observations():
    """THE LOOK-AHEAD PIN. test_the_panel_is_never_back_filled_before_the_first
    _observation only covers dates BEFORE the first observation — and those
    are independently blanked by the staleness mask (no preceding observation
    means an undefined age, which fails the freshness test). So that test
    passes even when _step_frame's ffill is swapped for a bfill, verified by
    mutation.

    The dangerous region is BETWEEN two observations, where a back-fill hands
    the formation date a short-interest value that was not published until
    later. Here AAA reports 1,000 shares short and then 9,000: every date
    between the two availability dates must still read 1,000."""
    index = bdays("2026-01-01", 120)
    close = close_frame(index, ["AAA"])
    ratio, dtc, _diag = build_short_interest_panels(
        close,
        {
            "AAA": [
                observation("2026-01-15", short=1_000.0, volume=100.0),
                observation("2026-01-30", short=9_000.0, volume=100.0),
            ]
        },
        share_frame(index, ["AAA"], 10_000.0),
    )
    first = pd.Timestamp(publication_date(date(2026, 1, 15)))
    second = pd.Timestamp(publication_date(date(2026, 1, 30)))
    between = (ratio.index >= first) & (ratio.index < second)
    assert between.any(), "fixture must straddle both availability dates"

    assert np.allclose(ratio.loc[between, "AAA"].to_numpy(), 0.1), (
        "a later cycle's short interest was visible before it was published"
    )
    assert np.allclose(dtc.loc[between, "AAA"].to_numpy(), 10.0)
    assert ratio.loc[ratio.index >= second, "AAA"].iloc[0] == pytest.approx(0.9)


def test_a_share_count_is_read_on_the_availability_date_itself_not_the_day_after():
    """The ratio's two inputs become jointly public on the LATER of their own
    availability dates, so the share count is read at the first trading day
    >= the short-interest availability date — `side="left"`. Mutation testing
    showed `side="right"` (which skips to the NEXT trading day, reading a
    share count the formation could not yet justify) left the suite green.

    Here the share panel steps from 10,000 to 50,000 on the trading day AFTER
    the availability date, so the two sides give different, distinguishable
    ratios: `left` reads 10,000 (ratio 0.1) and `right` would read the not-yet-
    justified 50,000 (ratio 0.02)."""
    index = bdays("2026-01-01", 120)
    close = close_frame(index, ["AAA"])
    available = pd.Timestamp(publication_date(date(2026, 1, 15)))
    assert available in index, "fixture must land the availability date on a trading day"
    day_after = index[index.searchsorted(available, side="left") + 1]

    shares = pd.DataFrame(10_000.0, index=index, columns=["AAA"])
    shares.loc[shares.index >= day_after, "AAA"] = 50_000.0

    ratio, _dtc, _diag = build_short_interest_panels(
        close, {"AAA": [observation("2026-01-15", short=1_000.0, volume=100.0)]}, shares
    )
    assert ratio.at[available, "AAA"] == pytest.approx(1_000.0 / 10_000.0), (
        "the share count was read a day late, admitting a count the formation "
        "could not yet justify"
    )


def test_the_short_interest_staleness_bound_is_pinned_to_its_documented_value():
    """NON-TAUTOLOGICAL companion to
    test_a_value_carried_past_the_staleness_bound_is_refused, which derives its
    own cutoff from SHORT_INTEREST_MAX_STALENESS_DAYS and therefore holds for
    any value, including one so large that a delisted name ranks forever.

    45 days is three consecutive missed bi-monthly cycles — the module's stated
    definition of disappearance rather than staleness."""
    assert SHORT_INTEREST_MAX_STALENESS_DAYS == 45

    index = bdays("2026-01-01", 200)
    close = close_frame(index, ["AAA"])
    ratio, _dtc, _diag = build_short_interest_panels(
        close,
        {"AAA": [observation("2026-01-15", short=1_000.0, volume=100.0)]},
        share_frame(index, ["AAA"], 10_000.0),
    )
    available = pd.Timestamp(publication_date(date(2026, 1, 15)))
    fresh = ratio.index[
        (ratio.index >= available) & (ratio.index <= available + pd.Timedelta(days=45))
    ]
    assert np.allclose(ratio.loc[fresh, "AAA"].to_numpy(), 0.1)
    # 45 is the real edge: one day past it the value is gone.
    stale = ratio.index[ratio.index > available + pd.Timedelta(days=45)]
    assert len(stale) > 0
    assert ratio.loc[stale, "AAA"].isna().all()


def test_the_cost_model_is_pinned_to_the_house_equity_rate():
    """Sharpes in this family are only comparable to the sibling S&P 500
    equity families because they are charged the same 5bp one-way. Mutation
    testing showed the cost could be silently set to zero — which flatters
    every spec, most of all the 21-day holds whose cost drag is ~10% — with
    the suite staying green."""
    from app.services.research_lab.cross_sectional import DEFAULT_XS_COST_BPS
    from app.services.research_lab.cross_sectional_short_interest import (
        SHORT_INTEREST_COST_BPS,
        SHORT_INTEREST_FINANCING_BPS_PER_YEAR,
        default_short_interest_config,
    )

    assert SHORT_INTEREST_COST_BPS == DEFAULT_XS_COST_BPS == 5.0
    # Disclosed optimism, pinned so it cannot become an unstated assumption.
    assert SHORT_INTEREST_FINANCING_BPS_PER_YEAR == 0.0
    config = default_short_interest_config()
    assert config.cost_bps == 5.0
    assert config.financing_bps_per_year == 0.0


def test_both_normalizer_passes_are_scored_against_the_full_twelve_trial_denominator():
    """THE VERDICT PIN, and the most consequential gap mutation testing found.

    The harness takes one fundamental_signal frame per call, so this family is
    screened as TWO passes of 6 specs. Each pass must be handed
    n_trials_override=12 — the full pre-declared grid — or the harness infers
    n_trials=6 and every DSR is deflated for half the search that really
    happened. Dropping the override left the suite green.

    It is not a cosmetic difference. On the real 2026-09-02 run the best spec
    si_dtc_ls_h63 scores DSR 0.948 at n_trials=12 and 0.961 at n_trials=6 —
    which would flip this family's pre-registered verdict from an honest
    negative into a spurious pass of the 0.95 bar.

    Screened here on a synthetic panel; what is asserted is the denominator
    that reaches deflated_sharpe, not any particular Sharpe."""
    from app.services.research_lab.cross_sectional import screen_cross_sectional_universe
    from app.services.research_lab.cross_sectional_short_interest import (
        default_short_interest_config,
    )

    # 120 names so a 5% leg is 6 -- above DEFAULT_MIN_NAMES_PER_LEG.
    index = bdays("2020-01-01", 900)
    tickers = [f"T{i:03d}" for i in range(120)]
    rng = np.random.default_rng(0)
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, size=(len(index), len(tickers))), axis=0)),
        index=index,
        columns=tickers,
    )
    panel = pd.DataFrame(
        rng.uniform(0.01, 0.30, size=(len(index), len(tickers))), index=index, columns=tickers
    )
    config = default_short_interest_config()
    config.formation_start = index[10].date()

    for normalizer in SHORT_INTEREST_NORMALIZERS:
        specs = specs_for_normalizer(normalizer)
        assert len(specs) == 6
        results = screen_cross_sectional_universe(
            CrossSectionalData(close=close, fundamental_signal=panel),
            specs,
            config,
            membership_fn=fixed_universe_membership(tickers),
            n_trials_override=SHORT_INTEREST_N_TRIALS,
        )
        assert results, "the pass produced no replayable spec"
        for result in results:
            assert result.deflated_sharpe.n_trials == SHORT_INTEREST_N_TRIALS == 12, (
                f"{result.pattern_id} was deflated for "
                f"{result.deflated_sharpe.n_trials} trials, not the family's 12"
            )


def test_the_production_entry_point_hands_BOTH_passes_the_twelve_trial_denominator():
    """THE VERDICT PIN AT ITS REAL CALL SITE.

    The test above proves screen_cross_sectional_universe honours an override
    it is given; this one proves run_short_interest_screening actually GIVES
    it. Mutation testing showed the `n_trials_override=SHORT_INTEREST_N_TRIALS`
    argument could be deleted from the production entry point with the whole
    suite staying green — and, because each pass screens only 6 specs, the
    harness would then infer n_trials=6 and deflate every DSR for half the
    search that really happened.

    On the real 2026-09-02 run that is the difference between DSR 0.948 (the
    recorded honest negative) and 0.961 (a spurious pass of the 0.95 bar), so
    this is pinned end to end with injected fakes rather than left to the
    caller's discipline."""
    from app.services.market_data.finra_short_interest_provider import (
        ShortInterestFetchDiagnostics,
    )
    from app.services.market_data.sec_shares_outstanding_provider import (
        ShareCountDiagnostics,
        ShareCountObservation,
    )
    from app.services.research_lab.cross_sectional_short_interest import (
        run_short_interest_screening,
    )

    # REAL, continuously-listed S&P 500 members: run_short_interest_screening
    # applies the project's real point-in-time membership gate (it takes no
    # membership_fn), so synthetic tickers would be refused by was_member and
    # the screen would raise EmptyEligibleUniverseError.
    tickers = STABLE_SP500_MEMBERS_FOR_FIXTURES
    index = bdays("2020-01-01", 900)
    rng = np.random.default_rng(7)
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, size=(len(index), len(tickers))), axis=0)),
        index=index,
        columns=tickers,
    )

    class FakePrices:
        def get_price_history(self, sample, start, end):
            return close, []

    class FakeFinra:
        def fetch_observations_for_tickers(self, priced, start, end):
            out = {}
            for position, ticker in enumerate(priced):
                out[ticker] = [
                    observation(
                        settlement.date().isoformat(),
                        short=1_000.0 + 10.0 * ((position + settlement.month) % 40),
                        volume=100.0 + ((position * 7 + settlement.month) % 50),
                        symbol=ticker,
                    )
                    for settlement in pd.date_range(index[0], index[-1], freq="15D")
                ]
            return out, ShortInterestFetchDiagnostics()

    class FakeShares:
        def fetch_share_counts(self, resolvable, start, end, *, missing_from_map=()):
            diagnostics = ShareCountDiagnostics()
            return {
                ticker: [
                    ShareCountObservation(
                        as_of=stamp.date(),
                        available=stamp.date(),
                        shares=50_000.0,
                    )
                    for stamp in pd.date_range(index[0], index[-1], freq="90D")
                ]
                for ticker in resolvable
            }, diagnostics

    class FakeEdgar:
        def get_ticker_cik_map(self):
            return {ticker: position for position, ticker in enumerate(tickers, start=1)}

    summary = run_short_interest_screening(
        start=index[10].date(),
        end=index[-1].date(),
        provider=FakePrices(),
        finra=FakeFinra(),
        sec_shares=FakeShares(),
        edgar=FakeEdgar(),
        universe=tickers,
    )

    assert summary.results, "the screen produced no replayable spec"
    assert summary.n_trials == SHORT_INTEREST_N_TRIALS == 12
    seen = {result.pattern_id for result in summary.results}
    assert len(seen) == 12, f"expected all 12 specs, saw {sorted(seen)}"
    for result in summary.results:
        assert result.deflated_sharpe.n_trials == 12, (
            f"{result.pattern_id} was deflated for {result.deflated_sharpe.n_trials} "
            "trials, not the family's pre-declared 12 — the DSR denominator was halved"
        )


# --- price_frames: the opt-in reproducibility override (2026-09-04) ---------


def _price_frames_screening_fixture():
    """The same fixed-provider shape
    test_the_production_entry_point_hands_BOTH_passes_the_twelve_trial_denominator
    already uses, refactored so the price_frames tests below can reuse it
    without duplicating the FakeFinra/FakeShares/FakeEdgar bodies."""
    from app.services.market_data.finra_short_interest_provider import (
        ShortInterestFetchDiagnostics,
    )
    from app.services.market_data.sec_shares_outstanding_provider import (
        ShareCountDiagnostics,
        ShareCountObservation,
    )

    tickers = STABLE_SP500_MEMBERS_FOR_FIXTURES
    index = bdays("2020-01-01", 900)
    rng = np.random.default_rng(7)
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, size=(len(index), len(tickers))), axis=0)),
        index=index,
        columns=tickers,
    )

    class FakeFinra:
        def fetch_observations_for_tickers(self, priced, start, end):
            out = {}
            for position, ticker in enumerate(priced):
                out[ticker] = [
                    observation(
                        settlement.date().isoformat(),
                        short=1_000.0 + 10.0 * ((position + settlement.month) % 40),
                        volume=100.0 + ((position * 7 + settlement.month) % 50),
                        symbol=ticker,
                    )
                    for settlement in pd.date_range(index[0], index[-1], freq="15D")
                ]
            return out, ShortInterestFetchDiagnostics()

    class FakeShares:
        def fetch_share_counts(self, resolvable, start, end, *, missing_from_map=()):
            diagnostics = ShareCountDiagnostics()
            return {
                ticker: [
                    ShareCountObservation(
                        as_of=stamp.date(),
                        available=stamp.date(),
                        shares=50_000.0,
                    )
                    for stamp in pd.date_range(index[0], index[-1], freq="90D")
                ]
                for ticker in resolvable
            }, diagnostics

    class FakeEdgar:
        def get_ticker_cik_map(self):
            return {ticker: position for position, ticker in enumerate(tickers, start=1)}

    return tickers, index, close, FakeFinra(), FakeShares(), FakeEdgar()


def test_price_frames_override_is_used_instead_of_a_live_fetch():
    """The whole point of the override (module docstring section 8, added
    2026-09-04 during the reproducibility investigation): when `price_frames`
    is supplied, `provider` must never be asked for a live price history at
    all. A `provider` that raises if touched pins the contract directly,
    the same way filing_index's "never calls text_provider" property is
    pinned in cross_sectional_lazy_prices' own tests."""
    from app.services.research_lab.cross_sectional_short_interest import (
        run_short_interest_screening,
    )

    tickers, index, close, finra, shares, edgar = _price_frames_screening_fixture()

    class PoisonPrices:
        def get_price_history(self, sample, start, end):
            raise AssertionError(
                "price_frames was supplied; the live provider must not be called"
            )

    summary = run_short_interest_screening(
        start=index[10].date(),
        end=index[-1].date(),
        provider=PoisonPrices(),
        finra=finra,
        sec_shares=shares,
        edgar=edgar,
        universe=tickers,
        price_frames={"close": close},
    )
    assert summary.results, "the screen produced no replayable spec"
    assert summary.n_trials == SHORT_INTEREST_N_TRIALS == 12


def test_price_frames_missing_columns_are_reported_as_missing_price_data():
    """A ticker absent from the frozen snapshot's columns must be counted
    exactly the way a live fetch's `missing` list already counts an
    unresolved ticker — not silently dropped, not a KeyError."""
    from app.services.research_lab.cross_sectional_short_interest import (
        run_short_interest_screening,
    )

    tickers, index, close, finra, shares, edgar = _price_frames_screening_fixture()
    dropped = tickers[0]
    trimmed_close = close.drop(columns=[dropped])

    summary = run_short_interest_screening(
        start=index[10].date(),
        end=index[-1].date(),
        provider=None,
        finra=finra,
        sec_shares=shares,
        edgar=edgar,
        universe=tickers,
        price_frames={"close": trimmed_close},
    )
    assert dropped in summary.missing_price_data
    assert len(summary.missing_price_data) == 1


def test_price_frames_replay_is_bit_identical_across_two_independent_calls():
    """THE VERDICT PIN for the reproducibility fix itself: two calls given
    the SAME frozen frame must produce the SAME Sharpe/DSR down to the
    float, not merely "close" — this is exactly the property a live fetch
    (module docstring section 8) does not have across separately-timed
    sessions, and is what makes a snapshot-pinned re-run trustworthy as a
    reference number."""
    from app.services.research_lab.cross_sectional_short_interest import (
        run_short_interest_screening,
    )

    tickers, index, close, finra, shares, edgar = _price_frames_screening_fixture()
    frames = {"close": close}

    runs = []
    for _ in range(2):
        summary = run_short_interest_screening(
            start=index[10].date(),
            end=index[-1].date(),
            provider=None,
            finra=finra,
            sec_shares=shares,
            edgar=edgar,
            universe=tickers,
            price_frames=frames,
        )
        runs.append(
            {r.pattern_id: (r.sharpe_annualized, r.deflated_sharpe.dsr) for r in summary.results}
        )

    assert runs[0], "the screen produced no replayable spec"
    assert runs[0] == runs[1], "the same frozen price frame must replay bit-identically"


# --- the post-hoc volume-confound diagnostic, now reproducible in code -------


def test_the_adv_panel_keeps_the_same_point_in_time_contract_as_the_ranking_panels():
    """FINRA's averageDailyVolumeQuantity is trailing by its own glossary
    definition, but it still only becomes READABLE when the cycle publishes.
    The diagnostic panel must therefore ride the identical availability and
    split contract as the panels it is compared against, or the confound
    measurement would be reading volume the formation could not see."""
    from app.services.research_lab.cross_sectional_short_interest import (
        build_average_daily_volume_panel,
    )

    index = bdays("2026-01-01", 60)
    close = close_frame(index, ["AAA"])
    adv = build_average_daily_volume_panel(
        close,
        {
            "AAA": [
                observation("2026-01-15", short=1_000.0, volume=250.0),
                observation("2026-01-30", short=1_000.0, volume=900.0, split=True),
            ]
        },
    )
    available = pd.Timestamp(publication_date(date(2026, 1, 15)))
    assert adv.loc[adv.index < available, "AAA"].isna().all()
    assert adv.at[available, "AAA"] == pytest.approx(250.0)
    # The split-flagged cycle is refused, exactly as in the ranking panels, so
    # the value never steps to 900.
    later = pd.Timestamp(publication_date(date(2026, 1, 30)))
    assert adv.loc[adv.index >= later, "AAA"].dropna().eq(250.0).all()


def test_the_divergence_diagnostic_separates_a_volume_sort_from_a_ratio_sort():
    """Pins the direction the real diagnostic reports. Constructed so the two
    normalizers DISAGREE by design: short interest is flat across names, so the
    ratio sort is driven by shares outstanding while days-to-cover is driven
    entirely by volume. The days-to-cover long leg must then sit high in the
    ADV distribution and the legs must barely overlap — the same signature
    measured on the real panel (72.7th ADV percentile, 19.7% overlap)."""
    from app.services.research_lab.cross_sectional_short_interest import (
        build_average_daily_volume_panel,
        measure_normalizer_divergence,
    )

    tickers = STABLE_SP500_MEMBERS_FOR_FIXTURES[:60]
    index = bdays("2021-01-01", 300)
    close = close_frame(index, tickers)

    observations = {}
    for position, ticker in enumerate(tickers):
        # Volume rises with position; shares outstanding FALLS with position.
        # So low days-to-cover = high volume = high position, while low ratio =
        # high shares outstanding = low position. The two legs are disjoint.
        observations[ticker] = [
            observation(
                stamp.date().isoformat(),
                short=1_000.0,
                volume=100.0 + 50.0 * position,
                symbol=ticker,
            )
            for stamp in pd.date_range("2021-01-15", "2022-01-15", freq="15D")
        ]
    shares = share_frame(
        index, tickers, {t: 1_000_000.0 - 5_000.0 * i for i, t in enumerate(tickers)}
    )
    ratio, dtc, _diag = build_short_interest_panels(close, observations, shares)
    adv = build_average_daily_volume_panel(close, observations).where(ratio.notna())

    result = measure_normalizer_divergence(
        close, ratio, dtc, adv, date(2021, 2, 1), holding_days=63
    )
    assert result.n_formations >= 2
    assert result.long_leg_overlap_share_of_leg == 0.0, "the legs were built disjoint"
    assert result.mean_adv_percentile_of_dtc_leg > 90.0
    assert result.mean_adv_percentile_of_ratio_leg < 20.0
    # Both are short/denominator with a constant numerator, and the two
    # denominators move oppositely here, so the rank correlation is negative.
    assert result.spearman_ratio_vs_dtc < 0.0
    assert 0.0 <= result.long_leg_overlap_jaccard <= result.long_leg_overlap_share_of_leg + 1e-9
