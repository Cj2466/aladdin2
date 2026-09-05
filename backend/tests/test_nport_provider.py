"""SEC Form N-PORT bulk provider: parsing, refusals, and the ZIP mechanics the
range-request reader depends on.

Nothing here touches the network. The ZIP tests build real archives in memory
with Python's own zipfile so the central-directory parser is checked against
bytes a real writer produced, not against a hand-rolled fixture that could
share the parser's own misunderstanding.
"""

from __future__ import annotations

import io
import struct
import zipfile
from datetime import date

import pytest

from app.services.market_data.nport_provider import (
    ASSET_CAT_EQUITY_COMMON,
    CUSIP_NOT_AVAILABLE,
    FIRST_BULK_QUARTER,
    UNIT_NUMBER_OF_SHARES,
    NportProvider,
    _read_zip64_extra,
    build_fund_quarter_filings,
    build_holding_rows,
    parse_float,
    parse_sec_date,
    published_quarters,
)

# --- date and number parsing --------------------------------------------------


def test_parse_sec_date_reads_the_dd_mon_yyyy_form_dera_actually_publishes():
    # Verbatim shapes from the real 2026q2 SUBMISSION.tsv.
    assert parse_sec_date("24-APR-2026") == date(2026, 4, 24)
    assert parse_sec_date("28-FEB-2026") == date(2026, 2, 28)
    assert parse_sec_date("01-JAN-2020") == date(2020, 1, 1)


def test_parse_sec_date_returns_none_rather_than_raising_on_as_filed_junk():
    """SEC's own README warns the tables "may contain redundancies,
    inconsistencies, and discrepancies". One bad cell must not abort a
    27-quarter sweep."""
    for junk in ("", "   ", "2026-04-24", "24-XXX-2026", "99-APR-2026", "not a date"):
        assert parse_sec_date(junk) is None


def test_parse_float_handles_the_bare_leading_decimal_nport_writes():
    assert parse_float(".0040692036") == pytest.approx(0.0040692036)
    assert parse_float("-225409.5") == pytest.approx(-225409.5)
    assert parse_float("0") == 0.0
    assert parse_float("") is None
    assert parse_float("N/A") is None


def test_published_quarters_starts_at_the_first_real_bulk_quarter():
    quarters = published_quarters(date(2020, 5, 15))
    assert quarters[0] == FIRST_BULK_QUARTER == "2019q4"
    assert quarters == ["2019q4", "2020q1", "2020q2"]
    # 27 quarterly ZIPs were live on 2026-09-05: 2019q4..2026q2, measured by
    # HTTP HEAD against every candidate, not assumed.
    assert published_quarters(date(2026, 6, 30)) == [
        f"{year}q{quarter}"
        for year in range(2019, 2027)
        for quarter in (1, 2, 3, 4)
        if "2019q4" <= f"{year}q{quarter}" <= "2026q2"
    ]
    assert len(published_quarters(date(2026, 6, 30))) == 27


def test_published_quarters_includes_the_in_progress_quarter():
    """It enumerates CANDIDATES through the calendar quarter containing
    `through`; the quarter currently in progress has no ZIP yet and 404s. The
    fetch script tolerates that per quarter rather than this function guessing
    at SEC's publication lag."""
    assert published_quarters(date(2026, 8, 31))[-1] == "2026q3"


# --- ZIP mechanics ------------------------------------------------------------


def _archive(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def test_central_directory_parser_agrees_with_pythons_own_zipfile():
    """The parser reads bytes a real ZIP writer produced, and every member's
    compressed size and local-header offset must match what zipfile reports."""
    payloads = {
        "SUBMISSION.tsv": b"a\tb\n1\t2\n" * 500,
        "FUND_REPORTED_HOLDING.tsv": b"x\ty\n" + b"row\trow\n" * 5000,
    }
    raw = _archive(payloads)
    provider = NportProvider(cache_dir=None)

    # Serve the archive from memory in place of HTTP.
    provider.content_length = lambda url: len(raw)  # type: ignore[method-assign]
    provider._range = lambda url, start, end, attempts=4: raw[start : end + 1]  # type: ignore[method-assign]

    directory = provider.central_directory("2026q2")
    with zipfile.ZipFile(io.BytesIO(raw)) as reference:
        for info in reference.infolist():
            member = directory[info.filename]
            assert member.compressed_size == info.compress_size
            assert member.uncompressed_size == info.file_size
            assert member.local_header_offset == info.header_offset


def test_stream_member_lines_reproduces_the_member_exactly():
    body = "\n".join(f"col_a_{i}\tcol_b_{i}" for i in range(20_000)) + "\n"
    raw = _archive({"FUND_REPORTED_HOLDING.tsv": body.encode()})
    provider = NportProvider(cache_dir=None)
    provider.content_length = lambda url: len(raw)  # type: ignore[method-assign]
    provider._range = lambda url, start, end, attempts=4: raw[start : end + 1]  # type: ignore[method-assign]

    lines = list(provider.stream_member_lines("2026q2", "FUND_REPORTED_HOLDING.tsv"))
    assert lines == body.split("\n")[:-1]


def test_extract_table_filters_while_streaming_and_caches(tmp_path):
    body = (
        "ACCESSION_NUMBER\tISSUER_CUSIP\tBALANCE\tUNIT\tCURRENCY_VALUE\tPERCENTAGE\tASSET_CAT\tCURRENCY_CODE\n"
        "acc1\t000000001\t10\tNS\t100\t1.0\tEC\tUSD\n"
        "acc1\t999999999\t20\tNS\t200\t2.0\tEC\tUSD\n"
        "acc2\t000000002\t30\tNS\t300\t3.0\tEC\tUSD\n"
    )
    raw = _archive({"FUND_REPORTED_HOLDING.tsv": body.encode()})
    provider = NportProvider(cache_dir=tmp_path)
    provider.content_length = lambda url: len(raw)  # type: ignore[method-assign]
    provider._range = lambda url, start, end, attempts=4: raw[start : end + 1]  # type: ignore[method-assign]

    rows = provider.holdings("2026q2", {"000000001", "000000002"})
    assert [r["ISSUER_CUSIP"] for r in rows] == ["000000001", "000000002"]

    # Second call is served from the cache: break the transport and re-read.
    def _boom(*args, **kwargs):
        raise AssertionError("cached table must not re-request")

    provider._range = _boom  # type: ignore[method-assign]
    provider.content_length = _boom  # type: ignore[method-assign]
    provider._directories.clear()
    assert provider.holdings("2026q2", {"000000001", "000000002"}) == rows


def test_zip64_extra_field_replaces_only_the_sentinel_fields():
    """Field order in the ZIP64 extended information record is uncompressed
    size, compressed size, local header offset — each present only when its
    32-bit counterpart is the 0xFFFFFFFF sentinel. Getting that conditional
    wrong silently reads the wrong 8 bytes."""
    body = struct.pack("<QQ", 111, 222)  # usize, csize present; offset absent
    extra = struct.pack("<HH", 0x0001, len(body)) + body
    csize, usize, offset = _read_zip64_extra(extra, 0xFFFFFFFF, 0xFFFFFFFF, 4096)
    assert (usize, csize, offset) == (111, 222, 4096)

    body = struct.pack("<Q", 999)  # only the offset is a sentinel
    extra = struct.pack("<HH", 0x0001, len(body)) + body
    csize, usize, offset = _read_zip64_extra(extra, 50, 60, 0xFFFFFFFF)
    assert (csize, usize, offset) == (50, 60, 999)


# --- filing and holding builders ---------------------------------------------


def _submission(accession: str, filing: str, report: str, sub_type: str = "NPORT-P") -> dict:
    return {
        "ACCESSION_NUMBER": accession,
        "FILING_DATE": filing,
        "SUB_TYPE": sub_type,
        "REPORT_DATE": report,
        "IS_LAST_FILING": "N",
    }


def _fund(accession: str, **overrides) -> dict:
    row = {
        "ACCESSION_NUMBER": accession,
        "SERIES_ID": "S000000001",
        "SERIES_NAME": "Test Fund",
        "TOTAL_ASSETS": "1100",
        "NET_ASSETS": "1000",
        "SALES_FLOW_MON1": "10",
        "REINVESTMENT_FLOW_MON1": "1",
        "REDEMPTION_FLOW_MON1": "5",
        "SALES_FLOW_MON2": "20",
        "REINVESTMENT_FLOW_MON2": "2",
        "REDEMPTION_FLOW_MON2": "6",
        "SALES_FLOW_MON3": "30",
        "REINVESTMENT_FLOW_MON3": "3",
        "REDEMPTION_FLOW_MON3": "7",
    }
    row.update(overrides)
    return row


def test_flow_fields_are_summed_across_the_quarters_three_months():
    filings, diagnostics = build_fund_quarter_filings(
        [_submission("a1", "29-AUG-2026", "30-JUN-2026")], [_fund("a1")]
    )
    assert len(filings) == 1
    filing = filings[0]
    assert filing.sales == pytest.approx(60.0)  # 10 + 20 + 30
    assert filing.reinvestment == pytest.approx(6.0)  # 1 + 2 + 3
    assert filing.redemption == pytest.approx(18.0)  # 5 + 6 + 7
    # Item B.6.a - Item B.6.c, the resolved definition.
    assert filing.external_flow_dollars == pytest.approx(42.0)
    # Item B.6.a + B.6.b - B.6.c, reported but NOT the project's definition.
    assert filing.net_flow_dollars == pytest.approx(48.0)
    assert diagnostics.n_filings_built == 1


def test_a_filing_dated_before_the_period_it_reports_on_is_refused():
    """Such a row would make a value visible before it existed. Refused, never
    trusted."""
    filings, diagnostics = build_fund_quarter_filings(
        [_submission("a1", "01-JAN-2026", "30-JUN-2026")], [_fund("a1")]
    )
    assert filings == []
    assert diagnostics.n_refused["filing_date_before_report_date"] == 1


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"NET_ASSETS": "0"}, "non_positive_net_assets"),
        ({"NET_ASSETS": "-5"}, "non_positive_net_assets"),
        ({"SERIES_ID": ""}, "missing_series_id"),
        ({"SALES_FLOW_MON2": ""}, "missing_sales_flow_mon2"),
    ],
)
def test_fund_row_refusals_are_counted_never_silent(overrides, reason):
    filings, diagnostics = build_fund_quarter_filings(
        [_submission("a1", "29-AUG-2026", "30-JUN-2026")], [_fund("a1", **overrides)]
    )
    assert filings == []
    assert diagnostics.n_refused[reason] == 1


def _holding(**overrides) -> dict:
    row = {
        "ACCESSION_NUMBER": "a1",
        "ISSUER_CUSIP": "037833100",
        "BALANCE": "1000",
        "UNIT": UNIT_NUMBER_OF_SHARES,
        "CURRENCY_VALUE": "150000",
        "PERCENTAGE": "1.25",
        "ASSET_CAT": ASSET_CAT_EQUITY_COMMON,
        "CURRENCY_CODE": "USD",
    }
    row.update(overrides)
    return row


def test_only_long_common_equity_positions_measured_in_shares_survive():
    rows, diagnostics = build_holding_rows(
        [
            _holding(),
            _holding(UNIT="PA"),  # a bond's principal amount is not a share count
            _holding(ASSET_CAT="DBT"),  # debt, not equity common
            _holding(ISSUER_CUSIP=CUSIP_NOT_AVAILABLE),
            _holding(BALANCE="-500"),  # a short position would invert the weight
            _holding(BALANCE="0"),
        ]
    )
    assert len(rows) == 1
    assert rows[0].shares == pytest.approx(1000.0)
    assert diagnostics.n_refused["not_number_of_shares"] == 1
    assert diagnostics.n_refused["not_equity_common"] == 1
    assert diagnostics.n_refused["cusip_not_available"] == 1
    assert diagnostics.n_refused["non_positive_shares"] == 2


def test_amendments_are_not_deduplicated_by_the_loader():
    """An NPORT-P/A supersedes its original only from ITS OWN filing date
    onward, so a point-in-time consumer must be able to see the original for
    dates before that. Deduplication is the consumer's decision."""
    filings, _ = build_fund_quarter_filings(
        [
            _submission("a1", "29-AUG-2026", "30-JUN-2026"),
            _submission("a2", "15-OCT-2026", "30-JUN-2026", sub_type="NPORT-P/A"),
        ],
        [_fund("a1"), _fund("a2", SALES_FLOW_MON1="999")],
    )
    assert len(filings) == 2
    assert {f.report_date for f in filings} == {date(2026, 6, 30)}
