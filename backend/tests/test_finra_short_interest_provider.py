"""Tests for the FINRA bi-monthly short interest provider.

The load-bearing one is
test_publication_lag_dominates_every_row_of_finras_published_schedule: it
pins the point-in-time bound against FINRA's own 2026 schedule, transcribed
verbatim below, so a future edit cannot silently shorten the lag below what
FINRA really publishes — which would be a look-ahead, not a tuning choice.

Everything else follows the house pattern: hand-built pipe-delimited
fixtures for the parser (real column names, real shapes), a fake session for
the fetch/retry/cache paths, and no network anywhere.
"""

from datetime import date, timedelta

import pytest
import requests

from app.services.market_data.finra_short_interest_provider import (
    EARLIEST_SETTLEMENT_DATE,
    PUBLICATION_LAG_CALENDAR_DAYS,
    FinraShortInterestFetchError,
    FinraShortInterestProvider,
    ShortInterestFetchDiagnostics,
    finra_symbol,
    publication_date,
    settlement_anchors,
)

# FINRA's published 2026 Short Interest Reporting Schedule, transcribed from
# https://www.finra.org/filing-reporting/regulatory-filing-systems/short-interest
# (fetched 2026-09-02): (settlement date, publication date). All 24 rows.
FINRA_2026_SCHEDULE: tuple[tuple[date, date], ...] = (
    (date(2026, 1, 15), date(2026, 1, 27)),
    (date(2026, 1, 30), date(2026, 2, 10)),
    (date(2026, 2, 13), date(2026, 2, 25)),
    (date(2026, 2, 27), date(2026, 3, 10)),
    (date(2026, 3, 13), date(2026, 3, 24)),
    (date(2026, 3, 31), date(2026, 4, 10)),
    (date(2026, 4, 15), date(2026, 4, 24)),
    (date(2026, 4, 30), date(2026, 5, 11)),
    (date(2026, 5, 15), date(2026, 5, 27)),
    (date(2026, 5, 29), date(2026, 6, 9)),
    (date(2026, 6, 15), date(2026, 6, 25)),
    (date(2026, 6, 30), date(2026, 7, 10)),
    (date(2026, 7, 15), date(2026, 7, 24)),
    (date(2026, 7, 31), date(2026, 8, 11)),
    (date(2026, 8, 14), date(2026, 8, 25)),
    (date(2026, 8, 31), date(2026, 9, 10)),
    (date(2026, 9, 15), date(2026, 9, 24)),
    (date(2026, 9, 30), date(2026, 10, 9)),
    (date(2026, 10, 15), date(2026, 10, 26)),
    (date(2026, 10, 30), date(2026, 11, 10)),
    (date(2026, 11, 13), date(2026, 11, 24)),
    (date(2026, 11, 30), date(2026, 12, 9)),
    (date(2026, 12, 15), date(2026, 12, 24)),
    (date(2026, 12, 31), date(2027, 1, 12)),
)

HEADER = (
    "accountingYearMonthNumber|symbolCode|issueName|issuerServicesGroupExchangeCode|"
    "marketClassCode|currentShortPositionQuantity|previousShortPositionQuantity|"
    "stockSplitFlag|averageDailyVolumeQuantity|daysToCoverQuantity|revisionFlag|"
    "changePercent|changePreviousNumber|settlementDate"
)


def row(
    symbol: str,
    short: str = "1000",
    volume: str = "500",
    settlement: str = "2026-08-14",
    market: str = "NYSE",
) -> str:
    return (
        f"20260814|{symbol}|{symbol} Inc.|A|{market}|{short}|900||{volume}|2.00||"
        f"1.0|100|{settlement}"
    )


def cycle(*rows: str) -> str:
    return "\n".join((HEADER, *rows)) + "\n"


class FakeResponse:
    def __init__(self, status_code: int = 200, content: bytes = b"") -> None:
        self.status_code = status_code
        self.content = content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


class FakeSession:
    """Records every URL asked for, so a test can assert the cache really
    prevented a request rather than merely returning the right bytes."""

    def __init__(self, responses: dict[str, FakeResponse] | None = None) -> None:
        self.responses = responses or {}
        self.headers: dict[str, str] = {}
        self.get_urls: list[str] = []
        self.head_urls: list[str] = []

    def get(self, url: str, timeout: float | None = None) -> FakeResponse:
        self.get_urls.append(url)
        return self.responses.get(url, FakeResponse(404))

    def head(self, url: str, timeout: float | None = None) -> FakeResponse:
        self.head_urls.append(url)
        return self.responses.get(url, FakeResponse(404))


def provider(session: FakeSession, tmp_path=None) -> FinraShortInterestProvider:
    return FinraShortInterestProvider(
        cache_dir=tmp_path, session=session, sleep=lambda _seconds: None
    )


def url_for(settlement: date) -> str:
    return f"https://cdn.finra.org/equity/otcmarket/biweekly/shrt{settlement:%Y%m%d}.csv"


def big(payload: str) -> bytes:
    """A fixture body padded past MIN_PLAUSIBLE_FILE_BYTES, so the
    truncated-download guard does not reject a legitimate test fixture. The
    padding is a comment-free trailing newline run, which csv.DictReader
    skips."""
    return (payload + "\n" * 200_000).encode()


# --- the point-in-time bound -------------------------------------------------


def test_publication_lag_dominates_every_row_of_finras_published_schedule():
    """THE load-bearing test of this module. If PUBLICATION_LAG_CALENDAR_DAYS
    were ever shortened below a real settlement-to-publication gap, every
    backtest built on this provider would read short interest before the
    public could — a look-ahead, not a parameter change."""
    for settlement, published in FINRA_2026_SCHEDULE:
        assert publication_date(settlement) >= published, (
            f"settlement {settlement} publishes {published} but this module would "
            f"admit it on {publication_date(settlement)} — that is a look-ahead."
        )


def test_the_lag_is_not_absurdly_conservative_either():
    """The other side of the same bound: a lag so long it skipped a whole
    reporting cycle would silently halve the signal's refresh rate. Every
    published gap is at least 9 days, and cycles are ~15 days apart, so the
    bound must sit between."""
    gaps = [(published - settlement).days for settlement, published in FINRA_2026_SCHEDULE]
    assert max(gaps) == 12
    assert PUBLICATION_LAG_CALENDAR_DAYS >= max(gaps)
    assert PUBLICATION_LAG_CALENDAR_DAYS < 15


def test_publication_date_is_a_pure_calendar_shift():
    assert publication_date(date(2026, 8, 14)) == date(2026, 8, 14) + timedelta(
        days=PUBLICATION_LAG_CALENDAR_DAYS
    )


# --- settlement anchors ------------------------------------------------------


def test_anchors_are_the_fifteenth_and_the_month_end():
    anchors = settlement_anchors(date(2026, 1, 1), date(2026, 3, 31))
    assert anchors == [
        date(2026, 1, 15),
        date(2026, 1, 31),
        date(2026, 2, 15),
        date(2026, 2, 28),
        date(2026, 3, 15),
        date(2026, 3, 31),
    ]


def test_anchors_handle_a_leap_february_and_a_year_boundary():
    anchors = settlement_anchors(date(2023, 12, 20), date(2024, 3, 1))
    assert date(2023, 12, 31) in anchors
    assert date(2024, 2, 29) in anchors
    assert date(2023, 12, 15) not in anchors  # before the requested start


def test_anchors_are_every_real_settlement_date_finra_published_in_2026():
    """Each real 2026 settlement date must be reachable from some anchor by
    the resolver's backward walk — the assumption the walk-back rests on."""
    anchors = set(settlement_anchors(date(2026, 1, 1), date(2026, 12, 31)))
    for settlement, _published in FINRA_2026_SCHEDULE:
        assert any(
            settlement + timedelta(days=back) in anchors for back in range(0, 7)
        ), f"{settlement} is not reachable from any anchor by a <=6 day backward walk"


# --- symbology ---------------------------------------------------------------


def test_finra_symbol_strips_share_class_separators():
    assert finra_symbol("BRK-B") == "BRKB"
    assert finra_symbol("BF-B") == "BFB"
    assert finra_symbol("AAPL") == "AAPL"


# --- parsing -----------------------------------------------------------------


def test_parse_reads_the_three_fields_and_derives_days_to_cover():
    parsed = FinraShortInterestProvider(cache_dir=None, session=FakeSession()).parse_cycle(
        cycle(row("AAPL", short="1000", volume="400"))
    )
    observation = parsed["AAPL"]
    assert observation.short_shares == 1000.0
    assert observation.average_daily_volume == 400.0
    assert observation.days_to_cover == pytest.approx(2.5)


def test_days_to_cover_is_recomputed_not_read_from_the_vendors_rounded_field():
    """The fixture's daysToCoverQuantity column says 2.00; the real ratio is
    2.5. Reading the vendor's 2-decimal field would quantize a ranking
    variable into thousands of ties (see the module docstring)."""
    parsed = FinraShortInterestProvider(cache_dir=None, session=FakeSession()).parse_cycle(
        cycle(row("AAPL", short="1000", volume="400"))
    )
    assert parsed["AAPL"].days_to_cover == pytest.approx(2.5)


def test_settlement_date_comes_from_the_row_not_the_caller():
    parsed = FinraShortInterestProvider(cache_dir=None, session=FakeSession()).parse_cycle(
        cycle(row("AAPL", settlement="2019-03-15"))
    )
    assert parsed["AAPL"].settlement_date == date(2019, 3, 15)
    assert parsed["AAPL"].available == publication_date(date(2019, 3, 15))


@pytest.mark.parametrize(
    ("bad_row", "reason"),
    [
        (row("DEAD", volume="0"), "non_positive_volume"),
        (row("DEAD", volume=""), "non_positive_volume"),
        (row("DEAD", volume="-5"), "non_positive_volume"),
        (row("DEAD", short="0"), "non_positive_short_interest"),
        (row("DEAD", short=""), "non_positive_short_interest"),
        (row("DEAD", short="not-a-number"), "unparseable_number"),
        (row("DEAD", settlement=""), "missing_settlement_date"),
    ],
)
def test_every_refusal_is_counted_and_the_row_is_dropped(bad_row: str, reason: str):
    diagnostics = ShortInterestFetchDiagnostics()
    parsed = FinraShortInterestProvider(cache_dir=None, session=FakeSession()).parse_cycle(
        cycle(bad_row), diagnostics=diagnostics
    )
    assert "DEAD" not in parsed
    assert diagnostics.n_rows_refused == {reason: 1}


def test_a_literal_double_quote_in_an_issue_name_does_not_corrupt_the_row():
    """REGRESSION, found on the real data during this build. FINRA's files
    are pipe-delimited with NO quoting, and issueName carries literal double
    quotes — this exact name appears in 68 of the 208 cached cycle files.
    Under csv's default QUOTE_MINIMAL the reader treats that quote as
    opening a quoted field and swallows delimiters and newlines until the
    next one, merging rows. Here the row AFTER the quoted one must still
    parse correctly and carry its own values."""
    body = cycle(
        '20260814|DOD|ELEMENTS "Dogs of the Dow" Tot|E|ARCA|12769|9938||13534|1.00||28.49|2|2026-08-14',
        row("AAPL", short="777", volume="7"),
    )
    parsed = FinraShortInterestProvider(cache_dir=None, session=FakeSession()).parse_cycle(body)
    assert parsed["DOD"].short_shares == 12769.0
    assert parsed["DOD"].average_daily_volume == 13534.0
    assert parsed["AAPL"].short_shares == 777.0
    assert parsed["AAPL"].settlement_date == date(2026, 8, 14)


def test_an_unbalanced_double_quote_still_leaves_later_rows_intact():
    """The dangerous case: an ODD number of quotes. Under the default
    dialect everything after it is swallowed into one field and every later
    security silently disappears from the cycle."""
    body = cycle(
        '20260814|ODD|SOME 12" PIPE CO|A|NYSE|100|90||10|10.00||1.0|1|2026-08-14',
        row("MSFT", short="555", volume="5"),
        row("NVDA", short="444", volume="4"),
    )
    parsed = FinraShortInterestProvider(cache_dir=None, session=FakeSession()).parse_cycle(body)
    assert set(parsed) == {"ODD", "MSFT", "NVDA"}
    assert parsed["NVDA"].short_shares == 444.0


def test_a_symbol_filter_restricts_what_is_parsed():
    parsed = FinraShortInterestProvider(cache_dir=None, session=FakeSession()).parse_cycle(
        cycle(row("AAPL"), row("MSFT"), row("NOPE")), symbols={"AAPL", "MSFT"}
    )
    assert set(parsed) == {"AAPL", "MSFT"}


def test_a_filtered_out_row_is_not_counted_as_a_refusal():
    """A row the caller never asked about is not a data defect, and counting
    it would bury the real refusals under ~20,000 OTC names per cycle."""
    diagnostics = ShortInterestFetchDiagnostics()
    FinraShortInterestProvider(cache_dir=None, session=FakeSession()).parse_cycle(
        cycle(row("NOPE", volume="0")), symbols={"AAPL"}, diagnostics=diagnostics
    )
    assert diagnostics.n_rows_refused == {}


# --- fetching, caching, retrying ---------------------------------------------


def test_fetch_writes_a_cache_file_and_a_second_call_makes_no_request(tmp_path):
    settlement = date(2026, 8, 14)
    session = FakeSession({url_for(settlement): FakeResponse(200, big(cycle(row("AAPL"))))})
    p = provider(session, tmp_path)

    first = p.fetch_raw(settlement)
    assert "AAPL" in first
    assert (tmp_path / "shrt20260814.csv").exists()

    second = p.fetch_raw(settlement)
    assert second == first
    assert len(session.get_urls) == 1  # the cache, not the network, served the second call


def test_a_truncated_two_hundred_byte_response_is_refused_not_cached(tmp_path):
    settlement = date(2026, 8, 14)
    session = FakeSession({url_for(settlement): FakeResponse(200, b"oops")})
    with pytest.raises(FinraShortInterestFetchError):
        provider(session, tmp_path).fetch_raw(settlement)
    assert not (tmp_path / "shrt20260814.csv").exists()
    assert len(session.get_urls) == 3  # all three attempts were made


def test_fetch_retries_then_raises_on_a_persistent_http_error(tmp_path):
    settlement = date(2026, 8, 14)
    session = FakeSession({url_for(settlement): FakeResponse(403)})
    with pytest.raises(FinraShortInterestFetchError):
        provider(session, tmp_path).fetch_raw(settlement)
    assert len(session.get_urls) == 3


def test_no_temp_file_survives_a_successful_write(tmp_path):
    settlement = date(2026, 8, 14)
    session = FakeSession({url_for(settlement): FakeResponse(200, big(cycle(row("AAPL"))))})
    provider(session, tmp_path).fetch_raw(settlement)
    assert (tmp_path / "shrt20260814.csv").exists()
    # Named suffix, not a whole-directory listing: this project's conftest
    # also drops a test.db into tmp_path, and asserting on the full listing
    # would couple this test to that unrelated fixture.
    assert [path.name for path in tmp_path.glob("*.tmp")] == []


# --- settlement-date resolution ----------------------------------------------


def test_a_weekend_anchor_walks_back_to_the_real_settlement_date(tmp_path):
    """2026-08-15 is a Saturday; FINRA's real settlement date is Friday the
    14th (its published schedule says "August 14 (Friday)")."""
    session = FakeSession({url_for(date(2026, 8, 14)): FakeResponse(200, b"x" * 200_000)})
    resolved, unresolved = provider(session, tmp_path).resolve_settlement_dates(
        date(2026, 8, 1), date(2026, 8, 20)
    )
    assert resolved == [date(2026, 8, 14)]
    assert unresolved == []
    # The Saturday itself is never even probed — the walk skips weekends.
    assert url_for(date(2026, 8, 15)) not in session.head_urls


def test_an_anchor_with_no_file_at_any_offset_is_reported_never_guessed(tmp_path):
    session = FakeSession({})
    resolved, unresolved = provider(session, tmp_path).resolve_settlement_dates(
        date(2026, 8, 1), date(2026, 8, 20)
    )
    assert resolved == []
    assert unresolved == [date(2026, 8, 15)]


def test_anchors_before_the_endpoints_first_file_are_skipped_without_probing(tmp_path):
    session = FakeSession({})
    start = EARLIEST_SETTLEMENT_DATE - timedelta(days=400)
    resolved, unresolved = provider(session, tmp_path).resolve_settlement_dates(
        start, EARLIEST_SETTLEMENT_DATE - timedelta(days=120)
    )
    assert resolved == []
    assert unresolved == []
    assert session.head_urls == []


def test_a_cached_file_resolves_without_any_head_request(tmp_path):
    (tmp_path / "shrt20260814.csv").write_bytes(b"x" * 200_000)
    session = FakeSession({})
    resolved, _unresolved = provider(session, tmp_path).resolve_settlement_dates(
        date(2026, 8, 1), date(2026, 8, 20)
    )
    assert resolved == [date(2026, 8, 14)]
    assert session.head_urls == []


# --- the production entry point ----------------------------------------------


def test_a_direct_symbol_match_wins_over_the_stripped_fallback(tmp_path):
    """Resolution order is load-bearing: stripping a separator can collide
    with an unrelated real symbol, so the direct form must be consulted
    first."""
    settlement = date(2026, 8, 14)
    body = cycle(row("BFB", short="111", volume="1"), row("BF-B", short="222", volume="1"))
    session = FakeSession({url_for(settlement): FakeResponse(200, big(body))})
    observations, diagnostics = provider(session, tmp_path).fetch_observations_for_tickers(
        ["BF-B"], date(2026, 8, 1), date(2026, 8, 20)
    )
    assert observations["BF-B"][0].short_shares == 222.0
    assert diagnostics.separator_stripped_matches == {}


def test_the_stripped_fallback_is_used_and_counted_when_the_direct_form_is_absent(tmp_path):
    settlement = date(2026, 8, 14)
    body = cycle(row("BRKB", short="333", volume="1"))
    session = FakeSession({url_for(settlement): FakeResponse(200, big(body))})
    observations, diagnostics = provider(session, tmp_path).fetch_observations_for_tickers(
        ["BRK-B"], date(2026, 8, 1), date(2026, 8, 20)
    )
    assert observations["BRK-B"][0].short_shares == 333.0
    assert diagnostics.separator_stripped_matches == {"BRK-B": 1}


def test_a_ticker_absent_from_the_cycle_gets_an_empty_list_never_a_zero(tmp_path):
    """A departed index member simply is not in that cycle's file. The
    correct answer is "no observation", which excludes it from ranking —
    never a fabricated zero short interest, which would rank it at the long
    leg's extreme."""
    settlement = date(2026, 8, 14)
    session = FakeSession({url_for(settlement): FakeResponse(200, big(cycle(row("AAPL"))))})
    observations, _diagnostics = provider(session, tmp_path).fetch_observations_for_tickers(
        ["AAPL", "GONE"], date(2026, 8, 1), date(2026, 8, 20)
    )
    assert observations["GONE"] == []
    assert len(observations["AAPL"]) == 1


def test_diagnostics_count_cycles_requested_and_resolved(tmp_path):
    session = FakeSession({url_for(date(2026, 8, 14)): FakeResponse(200, big(cycle(row("AAPL"))))})
    _observations, diagnostics = provider(session, tmp_path).fetch_observations_for_tickers(
        ["AAPL"], date(2026, 8, 1), date(2026, 8, 31)
    )
    assert diagnostics.n_cycles_requested == 2  # the 15th and the 31st
    assert diagnostics.n_cycles_resolved == 1
    assert diagnostics.unresolved_anchors == [date(2026, 8, 31)]
