"""Unit tests for app/services/market_data/cme_span_settlements.py.

Every expected value below is typed from a REAL record observed in
cme.20190102.s.pa2 (fetched live 2026-09-07) and the independent value it
must equal (Yahoo `=F` close or EIA NYMEX Contract-1 settle on the same
date), so the decoder is checked against the outside world, not against
itself. No network."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from app.services.market_data import cme_span_settlements as span

# (raw 7-digit field, locator, alignment) -> expected, with the independent source
DECODE_CASES = [
    ("0251100", 2, " ", 2511.00, "ES Mar-19 on 2019-01-02 = Yahoo ES=F close 2511.0"),
    ("0004654", 2, " ", 46.54, "CL Feb-19 on 2019-01-02 = EIA RCLC1 46.54 = Yahoo CL=F"),
    ("0004686", 2, " ", 46.86, "CL Mar-19 on 2019-01-02 = EIA RCLC2 46.86"),
    ("0295800", 5, " ", 2.958, "NG Feb-19 on 2019-01-02 = EIA RNGC1 2.958 = Yahoo NG=F"),
    ("0091905", 7, " ", 0.0091905, "6J Feb-19 (locator 7)"),
    ("0128100", 2, " ", 1281.00, "GC Jan-19 = Yahoo GC=F 1281.0"),
    ("0123525", 3, " ", 123.525, "LE Feb-19 = Yahoo LE=F 123.525"),
    ("0061700", 3, " ", 61.700, "HE Feb-19 = Yahoo HE=F 61.7"),
    ("0122060", 3, "C", 122.1875, "ZN Mar-19 = 122-06/32 = Yahoo ZN=F 122.1875"),
    ("0146240", 3, "C", 146.75, "ZB Mar-19 = 146-24/32 = Yahoo ZB=F 146.75"),
    ("0114220", 3, "C", 114.6875, "ZF Mar-19 = 114-22/32"),
    ("0106015", 3, "C", 106.046875, "ZT Mar-19 2019-01-15 = 106-01.5/32 (one 1/8-32nd tick below Yahoo's last)"),
    ("0106053", 3, "C", 106 + 5.375 / 32, "ZT Jun-19 2019-01-15, digit 3 = 3/8 (inferred display convention)"),
    ("0003757", 3, "0", 375.75, "ZC Mar-19 = Yahoo ZC=F 375.75 (quarter-cent code 7)"),
    ("0005067", 3, "0", 506.75, "ZW Mar-19 = Yahoo ZW=F 506.75"),
    ("0009070", 3, "0", 907.00, "ZS Mar-19 907'0"),
]


@pytest.mark.parametrize("raw,locator,alignment,expected,why", DECODE_CASES)
def test_decode_settlement_matches_independent_sources(raw, locator, alignment, expected, why):
    assert span.decode_settlement(raw, locator, alignment) == pytest.approx(expected, abs=1e-9), why


def test_negative_settlement_sign_is_honoured():
    # the real 2020-04-20 WTI May-20 settle was -37.63 (EIA RCLC1 carries it)
    assert span.decode_settlement("0003763", 2, " ", sign="-") == pytest.approx(-37.63)


@pytest.mark.parametrize("raw,alignment", [("0106054", "C"), ("0106059", "C"), ("0003754", "0"), ("0003759", "0")])
def test_unused_fraction_digits_are_refused_not_rounded(raw, alignment):
    with pytest.raises(span.SpanDecodeError):
        span.decode_settlement(raw, 3, alignment)


def test_unknown_alignment_code_is_refused():
    with pytest.raises(span.SpanDecodeError):
        span.decode_settlement("0001234", 2, "X")


# --- a tiny synthetic .pa2 built from the REAL record shapes ---------------

P_ES = "P CMEES        FUTE-MINI S&P 500 002000  000005000000000000000001USD$IDX 00    E-MINI S&P 500 FUTURES             YFFUT  CASH                  0000001000000000  "
P_ZN = "P CBT21        FUT10Y TREASURY NO003000C 000100000000000000000001USD$STD 00    10Y TREASURY NOTE FUTURES          YFFUT  DELIV                 0000001000000000  "
P_ZC = "P CBTC         FUTCORN FUTURES   0030000 000500000000000000000001USD$STD 00    CORN FUTURES                       YFFUT  DELIV                 0000001000000000  "
B_ES = "B CMEES        FUT201903            000000003500000006000030000330000000019726000000000200020190315ES          00000000         0000050000000000 00 00 010000000"
R81_ES = "81CMEES        ES        FUT 201903            000000000000+00000+02000-02000-02000+02000+04000-04000-04000+00000000251100N"
R82_ES = "82CMEES        ES        FUT 201903            000000004000+06000-06000-06000+06000+05940-05940+10000+000000000251100++10000+C"
R82_ZN = "82CBT21        21        FUT 201903            000000000700+01050-01050-01050+01050+01040-01040+10000+000000000122060++10000+C"
R82_ZC = "82CBTC         C         FUT 201903            000000000533+00800-00800-00800+00800+00792-00792+10000+000000000003757++10000+C"
R82_OTHER = "82CMEED        ED        FUT 201903            000000000533+00800-00800-00800+00800+00792-00792+10000+000000000097250++10000+C"
HEADER = "0 CME   20190102SF     201901021814U2YNCLR        C CUST  H HEDGE 1 CORE  M MAINT "


def _pa2_text() -> str:
    records = [HEADER, P_ES, P_ZN, P_ZC, B_ES, R81_ES, R82_ES, R82_ZN, R82_ZC, R82_OTHER]
    return "\n".join(records) + "\n"


def test_parse_products_reads_locator_and_alignment_at_documented_bytes():
    fmts = span.parse_products(_pa2_text().splitlines())
    assert fmts[("CME", "ES")].locator == 2 and fmts[("CME", "ES")].alignment == " "
    assert fmts[("CBT", "21")].locator == 3 and fmts[("CBT", "21")].alignment == "C"
    assert fmts[("CBT", "C")].locator == 3 and fmts[("CBT", "C")].alignment == "0"
    assert fmts[("CME", "ES")].long_name == "E-MINI S&P 500 FUTURES"


def test_parse_expirations_reads_ccyymmdd_at_bytes_92_99():
    exp = span.parse_expirations(_pa2_text().splitlines())
    assert exp[("CME", "ES", "201903")] == "20190315"  # ESH19 last trade 2019-03-15


def test_parse_pa2_text_decodes_target_rows_and_ignores_others():
    rows = span.parse_pa2_text(_pa2_text(), trade_date="2019-01-02")
    by = {r.globex: r for r in rows}
    assert set(by) == {"ES", "ZN", "ZC"}  # Eurodollar (ED) is not in the universe
    assert by["ES"].settle == pytest.approx(2511.0)
    assert by["ES"].raw_hp_settle == "00000000251100"
    assert by["ES"].expiration_date == "20190315"
    assert by["ZN"].settle == pytest.approx(122.1875)
    assert by["ZC"].settle == pytest.approx(375.75)


def test_parse_pa2_zip_takes_trade_date_from_header_when_not_given():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("cme.20190102.s.pa2", _pa2_text())
    rows = span.parse_pa2_zip(buf.getvalue())
    assert {r.trade_date for r in rows} == {"2019-01-02"}


def test_missing_price_format_is_an_error_not_a_guess():
    text = f"{HEADER}\n{R82_ES}\n"
    with pytest.raises(span.SpanDecodeError):
        span.parse_pa2_text(text, trade_date="2019-01-02")


def test_archive_url_layout_2013_monthly_vs_yearly():
    from datetime import date

    assert span.archive_url(date(2013, 1, 2)).endswith("/2013/201301/cme.20130102.s.pa2.zip")
    assert span.archive_url(date(2019, 1, 2)).endswith("/2019/cme.20190102.s.pa2.zip")


def test_store_roundtrip_and_manifest(tmp_path: Path):
    from datetime import date

    rows = span.parse_pa2_text(_pa2_text(), trade_date="2019-01-02")
    span.write_daily_rows(tmp_path, date(2019, 1, 2), rows)
    frame = span.load_daily(tmp_path)
    assert len(frame) == 3
    assert frame.loc[frame.globex == "ES", "settle"].iloc[0] == pytest.approx(2511.0)
    counts = span.write_per_instrument(tmp_path, frame)
    assert counts == {"ES": 1, "ZN": 1, "ZC": 1}
    manifest = span.write_manifest(tmp_path, frame)
    import json

    m = json.loads(manifest.read_text())
    assert m["per_instrument"]["ZC"]["unit"] == "cents per bushel"
    assert m["store_trade_days"] == 1


def test_every_universe_root_has_a_span_mapping():
    assert len(span.GLOBEX_TO_SPAN) == 31
    assert len(span.SPAN_TO_GLOBEX) == 31  # no two roots share a (exchange, code)
