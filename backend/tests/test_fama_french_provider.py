"""Tests for the Kenneth French FF3 monthly factor provider.

Two halves: hand-written fixtures pinning every parser guard (the annual
section, the missing-value sentinels, the percent/decimal contract, duplicate
and malformed rows), and a small set of assertions against the REAL committed
cache, because the whole point of committing that file is that a run's factor
vintage is reproducible — a test that only ever sees synthetic text would not
notice the cache going missing or being replaced by a different series.
"""

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.market_data.fama_french_provider import (
    FACTOR_COLUMNS,
    FAMA_FRENCH_MONTHLY_CACHE,
    load_fama_french_monthly,
    month_end,
    parse_fama_french_monthly,
)

# French's real layout in miniature: three preamble lines, a blank, the header,
# monthly YYYYMM rows, a blank, then the ANNUAL section with an identical header
# and 4-digit year keys.
FIXTURE = """This file was created using the 209912 CRSP database.
Some note about T-bills.
Another note.

,Mkt-RF,SMB,HML,RF
202001,   1.00,  -2.00,   3.00,   0.10
202002,  -4.00,   5.00,  -6.00,   0.20
202003,   7.50,   0.50,  -1.50,   0.30

 Annual Factors: January-December
,Mkt-RF,SMB,HML,RF
  2020,  29.44,  -2.20,  -4.58,   3.12
  2021,  35.56,   3.73,  -5.26,   3.56
"""


def test_parses_monthly_rows_into_decimal_month_end_frame():
    parsed = parse_fama_french_monthly(FIXTURE)
    assert list(parsed.frame.columns) == list(FACTOR_COLUMNS)
    assert list(parsed.frame.index) == [
        pd.Timestamp("2020-01-31"),
        pd.Timestamp("2020-02-29"),  # 2020 was a leap year — month-end, not day 28
        pd.Timestamp("2020-03-31"),
    ]
    # PERCENT in, DECIMAL out. 1.00 -> 0.01, not 1.00.
    assert parsed.frame.loc["2020-01-31", "mkt_rf"] == pytest.approx(0.01)
    assert parsed.frame.loc["2020-01-31", "smb"] == pytest.approx(-0.02)
    assert parsed.frame.loc["2020-01-31", "hml"] == pytest.approx(0.03)
    assert parsed.frame.loc["2020-01-31", "rf"] == pytest.approx(0.001)


def test_annual_section_is_not_spliced_into_the_monthly_series():
    """The annual section carries the SAME column header and plausible-looking
    numbers. Matching "a row starting with digits" would silently mix annual
    returns into a monthly series — which would look entirely healthy."""
    parsed = parse_fama_french_monthly(FIXTURE)
    assert len(parsed.frame) == 3
    # 29.44% (the 2020 ANNUAL market return) must appear nowhere.
    assert not np.isclose(parsed.frame.to_numpy(dtype=float), 0.2944).any()


def test_vintage_line_is_surfaced_as_provenance():
    parsed = parse_fama_french_monthly(FIXTURE)
    assert parsed.vintage_line == "This file was created using the 209912 CRSP database."


def test_missing_value_sentinels_become_nan_and_are_counted():
    text = FIXTURE.replace(
        "202002,  -4.00,   5.00,  -6.00,   0.20", "202002, -99.99,   5.00,-999.00,   0.20"
    )
    parsed = parse_fama_french_monthly(text)
    assert parsed.n_sentinel_cells == 2
    assert np.isnan(parsed.frame.loc["2020-02-29", "mkt_rf"])
    assert np.isnan(parsed.frame.loc["2020-02-29", "hml"])
    # The non-sentinel cells on the same row survive untouched.
    assert parsed.frame.loc["2020-02-29", "smb"] == pytest.approx(0.05)


def test_real_cache_has_no_sentinels_but_the_guard_is_not_conditional_on_that():
    """The committed vintage happens to be sentinel-free. The guard exists for
    the NEXT vintage, so it is tested on a fixture (above) rather than assumed
    dead because today's file does not trip it."""
    assert load_fama_french_monthly().n_sentinel_cells == 0


def test_percent_units_are_enforced_not_assumed():
    """A file already in decimal units (or a different series entirely) would
    otherwise be divided by 100 a second time, silently rescaling every beta by
    100x while leaving R^2 — the number a reader would check — unchanged."""
    text = FIXTURE.replace("202003,   7.50,", "202003, 750.00,")
    with pytest.raises(ValueError, match="implausible for a monthly factor return"):
        parse_fama_french_monthly(text)


def test_duplicate_months_are_refused():
    text = FIXTURE.replace(
        "202003,   7.50,   0.50,  -1.50,   0.30",
        "202003,   7.50,   0.50,  -1.50,   0.30\n202002,   1.00,   1.00,   1.00,   0.10",
    )
    with pytest.raises(ValueError, match="duplicate months"):
        parse_fama_french_monthly(text)


def test_short_row_is_refused_rather_than_padded():
    text = FIXTURE.replace("202003,   7.50,   0.50,  -1.50,   0.30", "202003,   7.50,   0.50")
    with pytest.raises(ValueError, match="value columns"):
        parse_fama_french_monthly(text)


def test_impossible_month_key_is_refused():
    text = FIXTURE.replace("202003,", "202013,")
    with pytest.raises(ValueError, match="not a valid YYYYMM"):
        parse_fama_french_monthly(text)


def test_empty_and_factorless_files_are_refused():
    with pytest.raises(ValueError, match="empty"):
        parse_fama_french_monthly("")
    with pytest.raises(ValueError, match="No monthly"):
        parse_fama_french_monthly("just a preamble\n\n,Mkt-RF,SMB,HML,RF\n")


def test_rows_are_sorted_even_if_the_file_is_not():
    text = """header
,Mkt-RF,SMB,HML,RF
202003,   7.50,   0.50,  -1.50,   0.30
202001,   1.00,  -2.00,   3.00,   0.10
"""
    parsed = parse_fama_french_monthly(text)
    assert parsed.frame.index.is_monotonic_increasing


def test_missing_cache_does_not_silently_download(tmp_path: Path):
    """A research run must use the committed vintage. A missing cache is an
    error, never a cue to reach for the network mid-backtest."""
    with pytest.raises(FileNotFoundError, match="does NOT download at run time"):
        load_fama_french_monthly(tmp_path / "absent.csv")


def test_month_end_helper_matches_the_frame_index_convention():
    assert month_end(date(2020, 2, 5)) == pd.Timestamp("2020-02-29")
    assert month_end(date(2021, 2, 5)) == pd.Timestamp("2021-02-28")
    assert month_end(date(2020, 12, 31)) == pd.Timestamp("2020-12-31")


# --- the real committed cache ------------------------------------------------


def test_committed_cache_exists_and_is_the_three_factor_monthly_series():
    assert FAMA_FRENCH_MONTHLY_CACHE.exists(), (
        "The committed Fama-French cache is missing. The residual-momentum family cannot run "
        "without it and deliberately will not download one at run time."
    )
    parsed = load_fama_french_monthly()
    assert list(parsed.frame.columns) == list(FACTOR_COLUMNS)
    assert parsed.frame.index.is_monotonic_increasing
    assert parsed.frame.index.is_unique
    # French's monthly 3-factor series starts July 1926. If this ever fails,
    # the cache has been replaced with a different series or a truncated file.
    assert parsed.first_month_end == pd.Timestamp("1926-07-31")
    assert parsed.last_month_end >= pd.Timestamp("2026-06-30")


def test_committed_cache_values_are_in_decimal_units_and_plausible():
    frame = load_fama_french_monthly().frame
    values = frame.to_numpy(dtype=float)
    values = values[np.isfinite(values)]
    # Decimal units: the worst month in the series is ~-30%, the best ~+40%.
    assert np.abs(values).max() < 1.0
    assert np.abs(values).max() > 0.05, "suspiciously flat — is this really percent/100?"
    # RF is a 1-month T-bill rate, so it is bounded above by a small number.
    rf = frame["rf"].dropna()
    assert rf.max() < 0.02
    # AND IT IS NOT ALWAYS POSITIVE. This test originally asserted rf >= 0 and
    # the real file falsified it: twelve months are very slightly negative, all
    # of them between 1933 and 1941, bottoming at -0.0006. That is a genuine
    # property of the historical T-bill series (bills briefly traded above par),
    # not a parse bug, so the assertion is corrected to the truth rather than
    # deleted. Nothing is negative anywhere in this family's backtest window,
    # which is what the next test pins.
    negative = rf[rf < 0]
    assert len(negative) == 12
    assert negative.index.max() < pd.Timestamp("1942-01-01")
    assert rf.min() > -0.001


def test_committed_cache_covers_the_families_backtest_window_with_room_for_the_window():
    """This family regresses over a 36-month rolling window ending two months
    before each formation, and formations start at MEMBERSHIP_DATA_START
    (2015-01-07). The factor file must therefore reach back to at least 2011."""
    frame = load_fama_french_monthly().frame
    assert frame.index[0] <= pd.Timestamp("2011-01-31")
    covered = frame.loc["2011-01-01":"2026-06-30"]
    assert covered.notna().all().all(), "gaps inside the backtest window"
    # No calendar month is skipped inside the window — a missing month would
    # shorten a 36-month regression window without anything else noticing.
    expected = pd.date_range("2011-01-31", covered.index[-1], freq="ME")
    assert list(covered.index) == list(expected)
    # And the risk-free rate is non-negative throughout THIS window, so the
    # excess returns this family regresses are not quietly inflated anywhere.
    assert (covered["rf"] >= 0).all()
