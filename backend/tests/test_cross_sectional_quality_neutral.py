"""Tests for the industry-neutral NOA family
(cross_sectional_quality_neutral.py) and its point-in-time SIC pipeline
(edgar_xbrl_provider.py's header/submissions additions).

Mirrors test_cross_sectional_quality.py's structure: family-shape
assertions, real-shaped fixtures for the data pipeline (here, SGML filing
headers modeled on the live-fetched Iron Mountain sequence), the
point-in-time bucket step panel's visibility rules, signal mechanics with
hand-computed demeaning, and — the load-bearing pair — synthetic
end-to-end proofs that the neutralization (a) KILLS a purely
sector-driven signal that fools the raw construction and (b) PRESERVES
genuine within-sector predictive power."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.market_data.edgar_xbrl_provider import (
    SicHistory,
    parse_filing_header_sic,
)
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    fixed_universe_membership,
    run_cross_sectional_backtest,
)
from app.services.research_lab.cross_sectional_quality import (
    NOA_FAMILY,
    QUALITY_RANK_FRACTION,
    QUALITY_ROBUSTNESS_RANK_FRACTION,
    signal_fundamental_factor,
)
from app.services.research_lab.cross_sectional_quality_neutral import (
    MIN_BUCKET_SIZE,
    NOA_NEUTRAL_DEMEAN_STATISTICS,
    NOA_NEUTRAL_DSR_N_TRIALS,
    NOA_NEUTRAL_HOLDING_DAYS,
    NOA_NEUTRAL_N_TRIALS,
    SECTOR_BUCKETS,
    _measure_bucket_drift,
    build_noa_neutral_family,
    build_point_in_time_bucket_frame,
    sic_to_bucket,
    signal_industry_demeaned_noa,
)
from app.services.research_lab.metrics import sharpe_ratio

# --- the frozen bucket map ---------------------------------------------------


def test_bucket_map_reproduces_the_verification_passes_named_assignments():
    """The tickers the raw family's verification pass named, with their
    live-fetched (2026-08-28) SIC codes: the long-decile fixtures VRSN/PFG
    must land in tech/financial and the short-decile REITs in reit —
    otherwise this family is not neutralizing the tilt that was actually
    diagnosed."""
    assert sic_to_bucket(7371) == "tech"  # VRSN
    assert sic_to_bucket(6321) == "financial"  # PFG
    assert sic_to_bucket(6798) == "reit"  # DOC, ARE, VICI
    assert sic_to_bucket(6510) == "reit"  # INVH
    assert sic_to_bucket(3571) == "tech"  # AAPL
    assert sic_to_bucket(4220) == "industrial"  # IRM pre-conversion (warehousing)


def test_bucket_map_carve_out_boundaries():
    # REITs are carved OUT of the finance division...
    assert sic_to_bucket(6500) == "reit"
    assert sic_to_bucket(6599) == "reit"
    # ...and everything else in 6000-6999 stays financial, including
    # health insurers (their balance sheets are insurer balance sheets).
    assert sic_to_bucket(6022) == "financial"  # state commercial banks
    assert sic_to_bucket(6324) == "financial"  # UNH-style health insurance
    assert sic_to_bucket(6770) == "financial"  # blank checks/holding
    # Cosmetics (2844) is consumer but paints (2851) is NOT — the range is
    # 2840-2849 only.
    assert sic_to_bucket(2844) == "consumer"
    assert sic_to_bucket(2851) == "industrial"
    # Software/IT services vs the rest of the 7300s business services.
    assert sic_to_bucket(7372) == "tech"
    assert sic_to_bucket(7389) == "industrial"
    assert sic_to_bucket(2834) == "healthcare"  # pharma
    assert sic_to_bucket(3841) == "healthcare"  # devices
    assert sic_to_bucket(8071) == "healthcare"  # labs
    assert sic_to_bucket(1311) == "energy_utility"  # oil & gas
    assert sic_to_bucket(4911) == "energy_utility"  # electric utility
    assert sic_to_bucket(4813) == "telecom_media"
    assert sic_to_bucket(7812) == "telecom_media"  # movies
    assert sic_to_bucket(5331) == "consumer"  # variety stores
    assert sic_to_bucket(3711) == "consumer"  # autos
    assert sic_to_bucket(3721) == "industrial"  # aircraft


def test_bucket_map_is_total_over_the_sic_code_space():
    for sic in range(0, 10000, 7):  # a dense sweep, every code must map
        assert sic_to_bucket(sic) in SECTOR_BUCKETS


# --- SGML header parsing -----------------------------------------------------

# Modeled byte-for-byte on the live-fetched IRM 2013 10-K header
# (accession 0001047469-13-002039, fetched 2026-08-28).
IRM_STYLE_HEADER = """<SEC-DOCUMENT>0001047469-13-002039.txt : 20130301
<SEC-HEADER>0001047469-13-002039.hdr.sgml : 20130301
<ACCEPTANCE-DATETIME>20130301124758
ACCESSION NUMBER:\t\t0001047469-13-002039
CONFORMED SUBMISSION TYPE:\t10-K

FILER:

\tCOMPANY DATA:\t
\t\tCOMPANY CONFORMED NAME:\t\t\tIRON MOUNTAIN INC
\t\tCENTRAL INDEX KEY:\t\t\t0001020569
\t\tSTANDARD INDUSTRIAL CLASSIFICATION:\tPUBLIC WAREHOUSING & STORAGE [4220]
\t\tIRS NUMBER:\t\t\t\t232588479
"""


def test_header_sic_parses_the_real_irm_shape():
    assert parse_filing_header_sic(IRM_STYLE_HEADER, 1020569) == 4220


def test_header_sic_attributes_to_the_requested_cik_among_cofilers():
    two_filers = IRM_STYLE_HEADER + (
        "\nFILER:\n\n\tCOMPANY DATA:\t\n"
        "\t\tCOMPANY CONFORMED NAME:\t\t\tSOME CO-REGISTRANT\n"
        "\t\tCENTRAL INDEX KEY:\t\t\t0000999999\n"
        "\t\tSTANDARD INDUSTRIAL CLASSIFICATION:\tREAL ESTATE INVESTMENT TRUSTS [6798]\n"
    )
    assert parse_filing_header_sic(two_filers, 1020569) == 4220
    assert parse_filing_header_sic(two_filers, 999999) == 6798


def test_header_sic_falls_back_to_first_when_cik_line_is_absent_and_none_when_no_sic():
    no_cik = "STANDARD INDUSTRIAL CLASSIFICATION:\tELECTRONIC COMPUTERS [3571]\n"
    assert parse_filing_header_sic(no_cik, 1020569) == 3571
    assert parse_filing_header_sic("CONFORMED SUBMISSION TYPE:\t10-K\n", 1020569) is None


# --- the point-in-time bucket step panel ------------------------------------


def bdays(start: str, periods: int) -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=periods)


def history(events: list[tuple[date, int | None]], current: int | None = None) -> SicHistory:
    return SicHistory(cik=1, events=events, current_sic=current)


def test_bucket_panel_switches_at_the_filing_date_never_before():
    """The IRM case: warehousing through the 2015 filing, REIT from the
    2016 filing date onward — the panel must show exactly that step."""
    close = pd.DataFrame(100.0, index=pd.bdate_range("2015-06-01", "2016-06-01"), columns=["IRM"])
    frame, no_bucket, fallback = build_point_in_time_bucket_frame(
        close,
        {"IRM": history([(date(2015, 2, 27), 4220), (date(2016, 2, 26), 6798)], current=6798)},
    )
    assert no_bucket == [] and fallback == []
    assert frame.loc["2015-06-01", "IRM"] == "industrial"
    assert frame.loc["2016-02-25", "IRM"] == "industrial"
    assert frame.loc["2016-02-26", "IRM"] == "reit"
    assert frame.loc["2016-06-01", "IRM"] == "reit"


def test_bucket_panel_never_backfills_before_the_first_header():
    """A converter's pre-observation history must not inherit its later
    label — cells before the first filing-dated SIC are NaN, and the name
    is simply never ranked there."""
    close = pd.DataFrame(100.0, index=bdays("2015-01-02", 60), columns=["AAA"])
    frame, _, _ = build_point_in_time_bucket_frame(
        close, {"AAA": history([(date(2015, 2, 2), 6798)])}
    )
    assert pd.isna(frame.loc["2015-01-30", "AAA"])
    assert frame.loc["2015-02-02", "AAA"] == "reit"


def test_bucket_panel_current_sic_fallback_only_when_no_header_ever_parsed():
    close = pd.DataFrame(100.0, index=bdays("2015-01-02", 10), columns=["AAA", "BBB", "CCC"])
    frame, no_bucket, fallback = build_point_in_time_bucket_frame(
        close,
        {
            "AAA": history([(date(2014, 3, 1), None)], current=3571),  # headers fetched, no SIC
            "BBB": history([(date(2014, 3, 1), 4911)], current=None),
        },
    )
    assert fallback == ["AAA"]
    assert (frame["AAA"] == "tech").all()
    assert (frame["BBB"] == "energy_utility").all()
    assert no_bucket == ["CCC"]  # no history at all
    assert frame["CCC"].isna().all()


# --- the signal: hand-computed demeaning ------------------------------------


def neutral_view(values: dict[str, float]) -> CrossSectionalData:
    index = bdays("2024-01-02", 5)
    close = pd.DataFrame(100.0, index=index, columns=list(values))
    frame = pd.DataFrame(np.nan, index=index, columns=list(values))
    frame.iloc[-1] = pd.Series(values)
    return CrossSectionalData(close=close, fundamental_signal=frame)


def constant_buckets(index: pd.DatetimeIndex, assignment: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        {t: pd.Series(b, index=index, dtype=object) for t, b in assignment.items()}, index=index
    )


def test_demeaning_matches_the_hand_computed_centers():
    """Two buckets of three: tech NOA {0.1, 0.2, 0.6} (mean 0.3), reit
    {0.7, 0.8, 1.2} (mean 0.9). Signal = -(NOA - bucket mean)."""
    view = neutral_view({"T1": 0.1, "T2": 0.2, "T3": 0.6, "R1": 0.7, "R2": 0.8, "R3": 1.2})
    buckets = constant_buckets(
        view.close.index,
        {"T1": "tech", "T2": "tech", "T3": "tech", "R1": "reit", "R2": "reit", "R3": "reit"},
    )
    signal = signal_industry_demeaned_noa(view, bucket_frame=buckets, statistic="mean")
    assert signal["T1"] == pytest.approx(0.2)  # -(0.1 - 0.3)
    assert signal["T3"] == pytest.approx(-0.3)  # -(0.6 - 0.3)
    assert signal["R1"] == pytest.approx(0.2)  # -(0.7 - 0.9): lean FOR A REIT
    assert signal["R3"] == pytest.approx(-0.3)
    # The leanest-for-its-industry names top the ranking regardless of
    # their raw level: R1's raw 0.7 outranks T3's raw 0.6.
    assert signal["R1"] > signal["T3"]


def test_a_purely_sector_driven_signal_demeans_to_exactly_zero():
    """THE construction's defining property: if NOA is nothing but a
    sector label (every member of a bucket identical), industry demeaning
    leaves NOTHING — all zeros, no ranking information at all."""
    view = neutral_view({"A1": 0.2, "A2": 0.2, "A3": 0.2, "B1": 0.9, "B2": 0.9, "B3": 0.9})
    buckets = constant_buckets(
        view.close.index,
        {"A1": "tech", "A2": "tech", "A3": "tech", "B1": "reit", "B2": "reit", "B3": "reit"},
    )
    for statistic in NOA_NEUTRAL_DEMEAN_STATISTICS:
        signal = signal_industry_demeaned_noa(view, bucket_frame=buckets, statistic=statistic)
        # atol only absorbs float epsilon from the mean subtraction
        # (pandas' mean of three identical 0.2s reconstructs 0.2 to
        # ~1e-17); the values carry no ranking information either way.
        assert np.allclose(signal.to_numpy(dtype=float), 0.0, atol=1e-12)


def test_median_demeaning_is_robust_to_a_bucket_outlier_where_mean_is_not():
    values = {"T1": 0.1, "T2": 0.2, "T3": 9.0, "R1": 0.7, "R2": 0.8, "R3": 1.2}
    buckets = constant_buckets(
        neutral_view(values).close.index,
        {"T1": "tech", "T2": "tech", "T3": "tech", "R1": "reit", "R2": "reit", "R3": "reit"},
    )
    view = neutral_view(values)
    mean_signal = signal_industry_demeaned_noa(view, bucket_frame=buckets, statistic="mean")
    median_signal = signal_industry_demeaned_noa(view, bucket_frame=buckets, statistic="median")
    # Median center for tech is 0.2 (untouched by the 9.0 outlier); the
    # mean center 3.1 drags every tech name's demeaned value with it.
    assert median_signal["T1"] == pytest.approx(0.1)
    assert mean_signal["T1"] == pytest.approx(3.0)


def test_min_bucket_size_refuses_thin_buckets_and_keeps_full_ones():
    assert MIN_BUCKET_SIZE == 3
    view = neutral_view({"T1": 0.1, "T2": 0.2, "T3": 0.6, "R1": 0.7, "R2": 0.8})
    buckets = constant_buckets(
        view.close.index,
        {"T1": "tech", "T2": "tech", "T3": "tech", "R1": "reit", "R2": "reit"},
    )
    signal = signal_industry_demeaned_noa(view, bucket_frame=buckets, statistic="mean")
    assert signal[["T1", "T2", "T3"]].notna().all()  # 3 members: kept
    assert signal[["R1", "R2"]].isna().all()  # 2 members: refused


def test_a_name_with_no_bucket_or_no_noa_is_refused():
    view = neutral_view({"T1": 0.1, "T2": 0.2, "T3": 0.6, "X1": 0.4, "T4": float("nan")})
    buckets = constant_buckets(
        view.close.index, {"T1": "tech", "T2": "tech", "T3": "tech", "T4": "tech"}
    )  # X1 has no bucket column at all
    signal = signal_industry_demeaned_noa(view, bucket_frame=buckets, statistic="mean")
    assert signal["X1"] != signal["X1"]  # NaN
    assert signal["T4"] != signal["T4"]  # NaN NOA stays NaN
    assert signal[["T1", "T2", "T3"]].notna().all()


def test_signal_raises_without_the_fundamental_frame_or_with_a_bogus_statistic():
    index = bdays("2024-01-02", 5)
    buckets = constant_buckets(index, {"AAA": "tech"})
    with pytest.raises(ValueError, match="fundamental_signal"):
        signal_industry_demeaned_noa(
            CrossSectionalData(close=pd.DataFrame(100.0, index=index, columns=["AAA"])),
            bucket_frame=buckets,
            statistic="mean",
        )
    with pytest.raises(ValueError, match="statistic"):
        signal_industry_demeaned_noa(
            neutral_view({"AAA": 0.1}), bucket_frame=buckets, statistic="zscore"
        )


def test_the_bucket_used_is_the_formation_dates_not_a_later_one():
    """A reclassification AFTER the formation date must not change the
    formation's demeaning — the signal reads the bucket panel at the
    view's own last timestamp, and the panel is a forward-filled step from
    filing dates."""
    index = bdays("2016-02-01", 40)
    close = pd.DataFrame(100.0, index=index, columns=["IRM", "T1", "T2", "D1", "D2"])
    frame = pd.DataFrame(np.nan, index=index, columns=close.columns)
    frame.loc[index[9]] = pd.Series({"IRM": 0.9, "T1": 0.1, "T2": 0.2, "D1": 0.7, "D2": 0.8})
    # IRM is industrial until a REIT reclassification filed at index[20].
    bucket_frame, _, _ = build_point_in_time_bucket_frame(
        close,
        {
            "IRM": history([(date(2015, 2, 27), 4220), (index[20].date(), 6798)]),
            "T1": history([(date(2015, 1, 1), 3571)]),
            "T2": history([(date(2015, 1, 1), 3571)]),
            "D1": history([(date(2015, 1, 1), 3721)]),
            "D2": history([(date(2015, 1, 1), 3721)]),
        },
    )
    view = CrossSectionalData(
        close=close.iloc[: 10], fundamental_signal=frame.iloc[: 10]
    )  # formation at index[9], BEFORE the reclassification
    signal = signal_industry_demeaned_noa(view, bucket_frame=bucket_frame, statistic="mean")
    # At formation, IRM is industrial: bucket {IRM 0.9, D1 0.7, D2 0.8},
    # mean 0.8 -> signal -(0.9 - 0.8) = -0.1. Were the later REIT label
    # leaking back, IRM would be a 1-member reit bucket and REFUSED.
    assert signal["IRM"] == pytest.approx(-0.1)
    assert signal[["T1", "T2"]].isna().all()  # 2-member tech bucket refused


# --- the pre-declared family -------------------------------------------------


def family_for_test() -> list[CrossSectionalSpec]:
    index = bdays("2024-01-02", 5)
    return build_noa_neutral_family(constant_buckets(index, {"AAA": "tech"}))


def test_family_is_exactly_nine_definitions_with_an_eighteen_trial_dsr_denominator():
    specs = family_for_test()
    assert len(specs) == NOA_NEUTRAL_N_TRIALS == 9
    assert NOA_NEUTRAL_DSR_N_TRIALS == 18
    assert NOA_NEUTRAL_DSR_N_TRIALS == NOA_NEUTRAL_N_TRIALS + len(NOA_FAMILY)


def test_family_covers_every_declared_axis_combination_exactly_once():
    specs = family_for_test()
    core = {(s.holding_days, s.pattern_id.rsplit("_", 1)[-1]) for s in specs if s.rank_fraction == QUALITY_RANK_FRACTION}
    assert core == {
        (h, stat) for h in NOA_NEUTRAL_HOLDING_DAYS for stat in NOA_NEUTRAL_DEMEAN_STATISTICS
    }
    quintiles = [s for s in specs if s.rank_fraction == QUALITY_ROBUSTNESS_RANK_FRACTION]
    assert sorted(s.holding_days for s in quintiles) == sorted(NOA_NEUTRAL_HOLDING_DAYS)
    assert all(s.portfolio == "long_short" for s in specs)
    assert all(s.family == "net_operating_assets_industry_neutral" for s in specs)


def test_family_pattern_ids_are_unique_and_disjoint_from_the_raw_noa_family():
    specs = family_for_test()
    ids = {s.pattern_id for s in specs}
    assert len(ids) == len(specs)
    assert ids.isdisjoint({s.pattern_id for s in NOA_FAMILY})


# --- end-to-end: the two load-bearing synthetic proofs ----------------------


def _sector_universe() -> tuple[list[str], list[str], pd.DatetimeIndex]:
    a = [f"AAA{i:02d}" for i in range(30)]
    b = [f"BBB{i:02d}" for i in range(30)]
    return a, b, bdays("2024-01-02", 220)


def _spec(signal_fn, rank_fraction: float = 0.1) -> CrossSectionalSpec:
    return CrossSectionalSpec(
        pattern_id="synthetic_probe",
        family="test",
        citation="test",
        signal_fn=signal_fn,
        lookback_days=1,
        holding_days=10,
        portfolio="long_short",
        rank_fraction=rank_fraction,
        requires_fundamental_signal=True,
    )


def test_a_pure_sector_artifact_fools_raw_noa_and_is_killed_by_neutralization():
    """The raw family's diagnosed failure mode, reproduced synthetically:
    NOA separates the two sectors cleanly (A ~0.2, B ~0.9) while its
    WITHIN-sector variation carries no return information, and returns
    are purely sector-driven (A drifts up, B down). The raw low-NOA sort
    must love this (it IS the sector bet); the industry-neutral sort must
    find ~nothing, because within sector there is nothing to find.

    The within-sector offsets are a deterministic interleaved grid — the
    i-th leanest A name and the i-th leanest B name have IDENTICAL
    demeaned values — so each neutral leg is exactly 3 A + 3 B with equal
    weight inside each tied pair, the sector drift cancels inside each
    leg BY CONSTRUCTION (asserted on the formation records below, not
    hoped for from a lucky draw), and the neutral stream is pure
    idiosyncratic noise."""
    a, b, index = _sector_universe()
    tickers = a + b
    rng = np.random.default_rng(20260828)
    drift = np.array([0.004] * len(a) + [-0.001] * len(b))
    daily = drift + rng.normal(0.0, 0.01, size=(len(index), len(tickers)))
    close = pd.DataFrame(
        100.0 * np.cumprod(1.0 + daily, axis=0), index=index, columns=tickers
    )
    # Interleaved within-sector offsets: A_i gets 0.0001*(2i+1), B_i gets
    # 0.0001*(2i+2); each sector's mean offset differs by exactly 0.0001,
    # so demeaned(A_i) == demeaned(B_i) pairwise.
    offsets_a = 0.0001 * (2 * np.arange(len(a)) + 1)
    offsets_b = 0.0001 * (2 * np.arange(len(b)) + 2)
    noa_values = np.concatenate([0.2 + offsets_a, 0.9 + offsets_b])
    noa = pd.DataFrame(
        np.tile(noa_values, (len(index), 1)), index=index, columns=tickers
    )
    buckets = constant_buckets(index, {t: "tech" for t in a} | {t: "reit" for t in b})
    data = CrossSectionalData(close=close, fundamental_signal=noa)
    config = CrossSectionalConfig()
    membership = fixed_universe_membership(tickers)

    raw = run_cross_sectional_backtest(
        data,
        _spec(lambda view: signal_fundamental_factor(view, direction=-1.0)),
        config,
        membership,
    )
    neutral = run_cross_sectional_backtest(
        data,
        _spec(
            lambda view: signal_industry_demeaned_noa(
                view, bucket_frame=buckets, statistic="mean"
            )
        ),
        config,
        membership,
    )
    raw_sharpe = sharpe_ratio(raw.daily_returns)
    neutral_sharpe = sharpe_ratio(neutral.daily_returns)
    # Raw legs are the pure sector bet the diagnosis found...
    first_raw = next(f for f in raw.formations if f.skipped_reason is None)
    assert set(first_raw.long_tickers) <= set(a)
    assert set(first_raw.short_tickers) <= set(b)
    # ...with a ~0.5%/day drift gap against ~1% idio noise: huge Sharpe.
    assert raw_sharpe > 5.0
    # Neutral legs are exactly sector-balanced at every formation —
    # the structural cancellation, asserted, not assumed.
    for f in neutral.formations:
        if f.skipped_reason is None:
            assert len(set(f.long_tickers) & set(a)) == 3
            assert len(set(f.long_tickers) & set(b)) == 3
            assert len(set(f.short_tickers) & set(a)) == 3
            assert len(set(f.short_tickers) & set(b)) == 3
    # What remains is idiosyncratic noise; an order of magnitude below
    # the raw artifact's Sharpe.
    assert abs(neutral_sharpe) < raw_sharpe / 4.0


def test_genuine_within_sector_predictive_power_survives_neutralization():
    """The converse proof: returns are driven ONLY by each name's NOA
    relative to its own sector (lean-for-its-industry drifts up), while
    the BETWEEN-sector NOA gap carries nothing (equal mean drift by
    construction). The neutral sort must find this signal at full
    strength, with legs drawing from BOTH sectors.

    No raw-vs-neutral contrast is asserted here, deliberately: in a
    two-sector toy where within-sector NOA order is monotone in drift,
    the raw sort's extreme deciles fall entirely inside one sector and so
    inherit the same within-sector ordering (its long leg is the leanest
    A names, which are also the highest-drift A names) — raw scoring well
    on THIS fixture is a property of the fixture, not evidence against
    the neutralization. The kill test above owns the contrast."""
    a, b, index = _sector_universe()
    tickers = a + b
    rng = np.random.default_rng(7)
    # Within-sector NOA offsets, symmetric around 0 in each sector.
    offsets_a = np.linspace(-0.05, 0.05, len(a))
    offsets_b = np.linspace(-0.05, 0.05, len(b))
    noa_values = np.concatenate([0.2 + offsets_a, 0.9 + offsets_b])
    # Drift: -k * (within-sector offset) -> lean-for-its-industry names
    # rise. Sector means are equal (both zero), so there is NO sector bet.
    k = 0.06
    drift = np.concatenate([-k * offsets_a, -k * offsets_b])
    daily = drift + rng.normal(0.0, 0.01, size=(len(index), len(tickers)))
    close = pd.DataFrame(
        100.0 * np.cumprod(1.0 + daily, axis=0), index=index, columns=tickers
    )
    noa = pd.DataFrame(np.tile(noa_values, (len(index), 1)), index=index, columns=tickers)
    buckets = constant_buckets(index, {t: "tech" for t in a} | {t: "reit" for t in b})
    data = CrossSectionalData(close=close, fundamental_signal=noa)
    config = CrossSectionalConfig()
    membership = fixed_universe_membership(tickers)

    neutral = run_cross_sectional_backtest(
        data,
        _spec(
            lambda view: signal_industry_demeaned_noa(
                view, bucket_frame=buckets, statistic="mean"
            )
        ),
        config,
        membership,
    )
    neutral_sharpe = sharpe_ratio(neutral.daily_returns)
    # Neutral longs the leanest-for-their-industry names from BOTH
    # sectors (drift +0.3%/day each) and shorts the most bloated
    # (-0.3%/day): a large, real Sharpe.
    assert neutral_sharpe > 4.0
    first_neutral = next(f for f in neutral.formations if f.skipped_reason is None)
    assert set(first_neutral.long_tickers) & set(a)
    assert set(first_neutral.long_tickers) & set(b)


# --- drift measurement -------------------------------------------------------


def test_bucket_drift_measurement_flags_the_irm_case():
    histories = {
        "IRM": history(
            [(date(2013, 3, 1), 4220), (date(2015, 2, 27), 4220), (date(2016, 2, 26), 6798)],
            current=6798,
        ),
        "AAPL": history([(date(2013, 1, 1), 3571), (date(2020, 1, 1), 3571)], current=3571),
    }
    drift, mismatch = _measure_bucket_drift(histories, date(2015, 1, 7), date(2026, 8, 27))
    assert drift == ["IRM"]  # bucket changed inside the window
    assert mismatch == ["IRM"]  # current-day bucket wrong for part of it
    # ...and a window entirely after the change sees no drift.
    drift_late, mismatch_late = _measure_bucket_drift(
        histories, date(2017, 1, 1), date(2026, 8, 27)
    )
    assert drift_late == [] and mismatch_late == []
