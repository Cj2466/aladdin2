"""Tests for the SEC Form 13F structured-data-set provider
(market_data/form13f_provider.py).

Covers the four things that can silently corrupt this pipeline: the
per-filing VALUE units defect, CUSIP and ticker normalisation, the
dated CUSIP->ticker map's time behaviour, and the archive parser's
refusal contract against real-shaped dirty rows.

Archive fixtures are built in-memory to the EXACT tab-separated shape of
the real SEC files (headers transcribed verbatim from the real 2016q1
archive), so the parser is exercised through its real code path rather
than around it. The production RUN uses only real downloaded SEC
archives; these fixtures exist so refusal branches that real data hits
rarely can be pinned deterministically.
"""

import io
import zipfile
from datetime import date

import pytest

from app.services.market_data.form13f_provider import (
    HOLDINGS_SUBMISSION_TYPES,
    VALUE_THOUSANDS_MULTIPLIER,
    CusipTickerMap,
    build_cusip_ticker_map,
    build_sec_user_agent,
    classify_value_scale,
    is_passive_filer_name,
    normalize_cusip,
    normalize_ticker,
    parse_ftd_archive,
    parse_quarter_archive,
    parse_sec_date,
)

# Headers transcribed verbatim from the real 2016q1 archive.
SUBMISSION_HEADER = "ACCESSION_NUMBER\tFILING_DATE\tSUBMISSIONTYPE\tCIK\tPERIODOFREPORT"
COVERPAGE_HEADER = (
    "ACCESSION_NUMBER\tREPORTCALENDARORQUARTER\tISAMENDMENT\tAMENDMENTNO\tAMENDMENTTYPE\t"
    "CONFDENIEDEXPIRED\tDATEDENIEDEXPIRED\tDATEREPORTED\tREASONFORNONCONFIDENTIALITY\t"
    "FILINGMANAGER_NAME\tFILINGMANAGER_STREET1\tFILINGMANAGER_STREET2\tFILINGMANAGER_CITY\t"
    "FILINGMANAGER_STATEORCOUNTRY\tFILINGMANAGER_ZIPCODE\tREPORTTYPE\tFORM13FFILENUMBER\t"
    "CRDNUMBER\tSECFILENUMBER\tPROVIDEINFOFORINSTRUCTION5\tADDITIONALINFORMATION"
)
INFOTABLE_HEADER = (
    "ACCESSION_NUMBER\tINFOTABLE_SK\tNAMEOFISSUER\tTITLEOFCLASS\tCUSIP\tFIGI\tVALUE\t"
    "SSHPRNAMT\tSSHPRNAMTTYPE\tPUTCALL\tINVESTMENTDISCRETION\tOTHERMANAGER\t"
    "VOTING_AUTH_SOLE\tVOTING_AUTH_SHARED\tVOTING_AUTH_NONE"
)


def _cover_row(accession: str, name: str) -> str:
    cells = [""] * 21
    cells[0] = accession
    cells[9] = name
    return "\t".join(cells)


def _info_row(
    accession: str,
    cusip: str,
    value: str,
    shares: str,
    *,
    kind: str = "SH",
    putcall: str = "",
    issuer: str = "ISSUER",
) -> str:
    cells = [""] * 15
    cells[0] = accession
    cells[1] = "1"
    cells[2] = issuer
    cells[3] = "COM"
    cells[4] = cusip
    cells[6] = value
    cells[7] = shares
    cells[8] = kind
    cells[9] = putcall
    return "\t".join(cells)


def build_archive(submissions: list[str], covers: list[str], infos: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("SUBMISSION.tsv", "\n".join([SUBMISSION_HEADER, *submissions]))
        archive.writestr("COVERPAGE.tsv", "\n".join([COVERPAGE_HEADER, *covers]))
        archive.writestr("INFOTABLE.tsv", "\n".join([INFOTABLE_HEADER, *infos]))
    return buffer.getvalue()


# --- identifier normalisation ------------------------------------------------


def test_normalize_cusip_accepts_real_cusips():
    assert normalize_cusip("037833100") == "037833100"
    assert normalize_cusip(" 30231g102 ") == "30231G102"


def test_normalize_cusip_pads_eight_character_numeric_prefix():
    """Some filers drop the leading zero of an all-numeric CUSIP."""
    assert normalize_cusip("37833100") == "037833100"


def test_normalize_cusip_does_not_pad_eight_character_garbage():
    """Regression: padding ANY 8-character value turned arbitrary garbage
    into a syntactically valid identifier. Only all-digit strings are
    plausibly a CUSIP that lost its leading zero."""
    assert normalize_cusip("BADCUSIP") is None
    assert normalize_cusip("ABCDEFGH") is None


def test_normalize_cusip_refuses_the_real_zero_row():
    """The real 2016q1 archive's FIRST INFOTABLE row carries CUSIP
    '0        ' with issuer name '0'. It must be refused, not padded into
    a plausible-looking identifier."""
    assert normalize_cusip("0        ") is None
    assert normalize_cusip("000000000") is None
    assert normalize_cusip("") is None
    assert normalize_cusip("NOTACUSIP!") is None


def test_normalize_ticker_converts_dot_class_to_dash():
    """SEC writes 'BRK.B'; this project's price universe uses 'BRK-B'.
    Measured during the build: without this, BRK-B and BF-B were the only
    two of 768 universe tickers failing to resolve for a format reason."""
    assert normalize_ticker("BRK.B") == "BRK-B"
    assert normalize_ticker(" bf.b ") == "BF-B"
    assert normalize_ticker("AAPL") == "AAPL"


def test_parse_sec_date_handles_the_real_convention():
    assert parse_sec_date("31-MAR-2016") == date(2016, 3, 31)
    assert parse_sec_date("2016-03-31") == date(2016, 3, 31)
    assert parse_sec_date("") is None
    assert parse_sec_date("garbage") is None


def test_build_sec_user_agent_is_contactable():
    assert "@" in build_sec_user_agent()


# --- the VALUE units defect --------------------------------------------------


def test_classify_value_scale_detects_thousands():
    """A filing reporting in thousands implies sub-dollar 'prices'."""
    assert classify_value_scale([0.105, 0.052, 0.201]) == VALUE_THOUSANDS_MULTIPLIER


def test_classify_value_scale_detects_whole_dollars():
    assert classify_value_scale([105.0, 52.0, 201.0]) == 1.0


def test_classify_value_scale_uses_median_not_mean():
    """A handful of corrupt rows inside an otherwise sane filing must not
    flip the whole book's unit scale."""
    assert classify_value_scale([0.1, 0.1, 0.1, 0.1, 9999.0]) == VALUE_THOUSANDS_MULTIPLIER


def test_classify_value_scale_refuses_the_incredible():
    assert classify_value_scale([]) is None
    assert classify_value_scale([1e9, 1e9]) is None
    assert classify_value_scale([1e-9, 1e-9]) is None


def test_parse_quarter_archive_normalizes_a_thousands_filing_to_dollars():
    """End-to-end on the defect: a filing reporting VALUE in thousands
    comes back in whole dollars, so it is comparable across filings."""
    archive = build_archive(
        ["0000000000-16-000001\t15-FEB-2016\t13F-HR\t1234\t31-DEC-2015"],
        [_cover_row("0000000000-16-000001", "SOME ADVISORS LP")],
        [
            # 1,000 shares at ~$105 reported as 105 (thousands).
            _info_row("0000000000-16-000001", "037833100", "105", "1000"),
            _info_row("0000000000-16-000001", "594918104", "52", "1000"),
            _info_row("0000000000-16-000001", "30231G102", "20", "1000"),
        ],
    )
    filings, diagnostics = parse_quarter_archive(archive)
    assert len(filings) == 1
    filing = filings[0]
    assert filing.value_scale == VALUE_THOUSANDS_MULTIPLIER
    assert filing.holdings["037833100"] == pytest.approx(105_000.0)
    assert filing.total_value_usd == pytest.approx(177_000.0)
    assert diagnostics.value_scale_counts["thousands"] == 1


def test_portfolio_weights_are_immune_to_the_units_defect():
    """THE load-bearing property of section 2: a portfolio weight is a
    ratio of two same-unit numbers, so a mis-scaled filing still produces
    exactly correct weights. Two identical books reported in different
    units must yield identical weights."""
    rows_thousands = [
        _info_row("A-1", "037833100", "105", "1000"),
        _info_row("A-1", "594918104", "52", "1000"),
        _info_row("A-1", "30231G102", "20", "1000"),
    ]
    rows_dollars = [
        _info_row("B-1", "037833100", "105000", "1000"),
        _info_row("B-1", "594918104", "52000", "1000"),
        _info_row("B-1", "30231G102", "20000", "1000"),
    ]
    archive = build_archive(
        [
            "A-1\t15-FEB-2016\t13F-HR\t1\t31-DEC-2015",
            "B-1\t15-FEB-2016\t13F-HR\t2\t31-DEC-2015",
        ],
        [_cover_row("A-1", "ADVISOR A"), _cover_row("B-1", "ADVISOR B")],
        rows_thousands + rows_dollars,
    )
    filings, _ = parse_quarter_archive(archive)
    by_accession = {f.accession: f for f in filings}
    a, b = by_accession["A-1"], by_accession["B-1"]
    assert a.value_scale != b.value_scale
    for cusip in ("037833100", "594918104", "30231G102"):
        assert a.holdings[cusip] / a.total_value_usd == pytest.approx(
            b.holdings[cusip] / b.total_value_usd
        )


# --- the parser's refusal contract -------------------------------------------


def test_parse_quarter_archive_refuses_options_and_debt_and_bad_rows():
    archive = build_archive(
        ["A-1\t15-FEB-2016\t13F-HR\t1\t31-DEC-2015"],
        [_cover_row("A-1", "ADVISOR A")],
        [
            _info_row("A-1", "037833100", "105", "1000"),
            _info_row("A-1", "594918104", "52", "1000"),
            _info_row("A-1", "30231G102", "20", "1000"),
            _info_row("A-1", "88160R101", "99", "1000", putcall="Call"),
            _info_row("A-1", "912828XY9", "99", "1000", kind="PRN"),
            _info_row("A-1", "0        ", "0", "0", issuer="0"),
            _info_row("A-1", "023135106", "-5", "1000"),
            _info_row("A-1", "023135106", "notanumber", "1000"),
        ],
    )
    filings, diagnostics = parse_quarter_archive(archive)
    assert len(filings) == 1
    assert set(filings[0].holdings) == {"037833100", "594918104", "30231G102"}
    assert diagnostics.n_refused["option_position"] == 1
    assert diagnostics.n_refused["not_share_denominated"] == 1
    assert diagnostics.n_refused["malformed_cusip"] == 1
    assert diagnostics.n_refused["non_positive_value"] == 1
    assert diagnostics.n_refused["unparseable_numeric"] == 1


def test_parse_quarter_archive_drops_notice_filings():
    """13F-NT carries no holdings; admitting it would create phantom
    zero-holding managers."""
    archive = build_archive(
        [
            "A-1\t15-FEB-2016\t13F-HR\t1\t31-DEC-2015",
            "N-1\t15-FEB-2016\t13F-NT\t2\t31-DEC-2015",
        ],
        [_cover_row("A-1", "ADVISOR A"), _cover_row("N-1", "NOTICE FILER")],
        [
            _info_row("A-1", "037833100", "105", "1000"),
            _info_row("A-1", "594918104", "52", "1000"),
        ],
    )
    filings, diagnostics = parse_quarter_archive(archive)
    assert [f.accession for f in filings] == ["A-1"]
    assert diagnostics.n_refused["submission_type_13F-NT"] == 1
    assert "13F-NT" not in HOLDINGS_SUBMISSION_TYPES


def test_parse_quarter_archive_refuses_a_filing_dated_before_its_period():
    """A report cannot become public before the quarter it describes has
    ended; admitting one would inject look-ahead directly."""
    archive = build_archive(
        ["A-1\t01-DEC-2015\t13F-HR\t1\t31-DEC-2015"],
        [_cover_row("A-1", "ADVISOR A")],
        [_info_row("A-1", "037833100", "105", "1000")],
    )
    filings, diagnostics = parse_quarter_archive(archive)
    assert filings == []
    assert diagnostics.n_refused["filed_before_period_end"] == 1


def test_parse_quarter_archive_sums_duplicate_cusip_lines():
    """A manager legitimately reports one security on several lines when
    it is split across discretion categories. Taking only one line would
    UNDERSTATE exactly the largest-conviction names this family hunts."""
    archive = build_archive(
        ["A-1\t15-FEB-2016\t13F-HR\t1\t31-DEC-2015"],
        [_cover_row("A-1", "ADVISOR A")],
        [
            _info_row("A-1", "037833100", "60", "600"),
            _info_row("A-1", "037833100", "45", "400"),
            _info_row("A-1", "594918104", "52", "1000"),
        ],
    )
    filings, _ = parse_quarter_archive(archive)
    assert filings[0].holdings["037833100"] == pytest.approx(105_000.0)
    assert filings[0].n_holdings == 2


def test_parse_quarter_archive_reads_tables_nested_in_a_directory():
    """Regression, from a real production failure: SEC's archives are not
    internally consistent about layout. 52 of the 53 archives this family
    downloads store tables at the archive root; 01jun2025-31aug2025 nests
    them under a directory. An exact-path lookup parsed 52 quarters and
    then died on the 53rd."""
    buffer = io.BytesIO()
    prefix = "01JUN2025-31AUG2025_form13f/"
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            prefix + "SUBMISSION.tsv",
            "\n".join([SUBMISSION_HEADER, "A-1\t15-AUG-2025\t13F-HR\t1\t30-JUN-2025"]),
        )
        archive.writestr(
            prefix + "COVERPAGE.tsv",
            "\n".join([COVERPAGE_HEADER, _cover_row("A-1", "ADVISOR A")]),
        )
        archive.writestr(
            prefix + "INFOTABLE.tsv",
            "\n".join(
                [
                    INFOTABLE_HEADER,
                    _info_row("A-1", "037833100", "105", "1000"),
                    _info_row("A-1", "594918104", "52", "1000"),
                ]
            ),
        )
    filings, _ = parse_quarter_archive(buffer.getvalue())
    assert len(filings) == 1
    assert filings[0].n_holdings == 2


def test_parse_quarter_archive_records_the_amendment_flag():
    archive = build_archive(
        ["A-2\t20-MAR-2016\t13F-HR/A\t1\t31-DEC-2015"],
        [_cover_row("A-2", "ADVISOR A")],
        [_info_row("A-2", "037833100", "105", "1000")],
    )
    filings, _ = parse_quarter_archive(archive)
    assert filings[0].is_amendment


# --- fails-to-deliver / CUSIP map --------------------------------------------


def _ftd_archive(lines: list[str]) -> bytes:
    buffer = io.BytesIO()
    header = "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE"
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("cnsfails201603a.txt", "\n".join([header, *lines]))
    return buffer.getvalue()


def test_parse_ftd_archive_reads_the_real_pipe_format():
    payload = _ftd_archive(
        [
            "20160301|037833100|AAPL|52|APPLE INC|105.26",
            "20160301|084670702|BRK.B|10|BERKSHIRE HATHAWAY|140.00",
            "20160301|BADCUSIP|XX|1|JUNK|1.00",
            "not a row",
        ]
    )
    triples = parse_ftd_archive(payload)
    assert (date(2016, 3, 1), "037833100", "AAPL") in triples
    # Dot-class tickers are normalised on the way in.
    assert (date(2016, 3, 1), "084670702", "BRK-B") in triples
    assert len(triples) == 2


def test_cusip_map_restricts_to_universe():
    triples = [
        (date(2016, 3, 1), "037833100", "AAPL"),
        (date(2016, 3, 1), "999999999", "NOTINUNIVERSE"),
    ]
    mapping = build_cusip_ticker_map(triples, restrict_to={"AAPL"})
    assert mapping.resolve("037833100", date(2016, 3, 31)) == "AAPL"
    assert mapping.resolve("999999999", date(2016, 3, 31)) is None


def test_cusip_map_resolves_by_nearest_observation_in_time():
    """Both identifiers get recycled on corporate actions, so a flat
    all-time dictionary would apply a later reassignment to an earlier
    filing. Resolution is nearest-in-time instead."""
    mapping = CusipTickerMap(
        {"111111111": [(date(2015, 1, 1), "OLD"), (date(2024, 1, 1), "NEW")]}
    )
    assert mapping.resolve("111111111", date(2015, 6, 1)) == "OLD"
    assert mapping.resolve("111111111", date(2023, 6, 1)) == "NEW"
    assert mapping.resolve("222222222", date(2015, 6, 1)) is None


# --- the passive filer screen ------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "VANGUARD GROUP INC",
        "BLACKROCK INC.",
        "SPDR STATE STREET",
        "ISHARES TRUST",
        "SOME INDEX FUND LLC",
        "GEODE CAPITAL MANAGEMENT",
        "DIMENSIONAL FUND ADVISORS LP",
    ],
)
def test_passive_screen_catches_the_big_indexers(name):
    """The largest passive complexes do not put 'INDEX' in their filer
    name, so a purely generic screen would let exactly the biggest
    closet-indexers through."""
    assert is_passive_filer_name(name)


@pytest.mark.parametrize(
    "name",
    ["BERKSHIRE HATHAWAY INC", "PERSHING SQUARE CAPITAL MANAGEMENT", "BAUPOST GROUP LLC"],
)
def test_passive_screen_keeps_discretionary_managers(name):
    assert not is_passive_filer_name(name)
