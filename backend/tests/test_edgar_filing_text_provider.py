"""Unit tests for the EDGAR filing FULL-TEXT provider, mirroring
test_yfinance_provider.py's structure: synthetic fixtures for the pure
parsing/extraction logic, an httpx.MockTransport for the fetch paths, and NO
live network calls anywhere.

The real EDGAR shapes exercised here (submissions parallel arrays including
primaryDocument and acceptanceDateTime, the paginated filings.files older-history
documents, and the Archives primary-document URL) were verified LIVE against
data.sec.gov and www.sec.gov on 2026-09-01 during the build session; every
fixture below is a recorded-shape reproduction of what those endpoints
actually returned, so CI never touches SEC.
"""

from datetime import date

import httpx
import pytest

from app.services.market_data.edgar_filing_text_provider import (
    MAX_SECTION_DOC_FRACTION,
    MIN_SECTION_CHARS,
    EdgarFetchError,
    EdgarFilingTextProvider,
    FilingRef,
    availability_date,
    extract_section,
    html_to_text,
    load_filing_index,
    parse_filing_rows,
    save_filing_index,
)

# --- shared synthetic fixtures ---------------------------------------------


def _filing(
    accession: str = "0000320193-25-000079",
    form: str = "10-K",
    filing_date: date = date(2025, 10, 31),
    acceptance: str = "2025-10-31T10:01:26.000Z",
    report_date: date | None = date(2025, 9, 27),
    primary: str = "aapl-20250927.htm",
    cik: int = 320193,
) -> FilingRef:
    return FilingRef(
        cik=cik,
        accession=accession,
        form=form,
        filing_date=filing_date,
        acceptance_utc=acceptance,
        report_date=report_date,
        primary_document=primary,
    )


def _submissions(rows: list[dict], files: list[dict] | None = None) -> dict:
    """The recorded filings.recent parallel-array shape."""
    keys = (
        "accessionNumber",
        "filingDate",
        "reportDate",
        "acceptanceDateTime",
        "form",
        "primaryDocument",
    )
    return {
        "cik": "320193",
        "filings": {
            "recent": {k: [r.get(k, "") for r in rows] for k in keys},
            "files": files or [],
        },
    }


def _row(
    accession: str,
    form: str,
    filing_date: str,
    *,
    report: str = "",
    acceptance: str = "",
    primary: str = "doc.htm",
) -> dict:
    return {
        "accessionNumber": accession,
        "filingDate": filing_date,
        "reportDate": report,
        "acceptanceDateTime": acceptance,
        "form": form,
        "primaryDocument": primary,
    }


def _padding(words: int = 400) -> str:
    return "<p>" + ("other filing content " * words) + "</p>"


# --- html_to_text: the inline-XBRL contaminant -----------------------------


def test_inline_xbrl_header_block_is_removed_before_any_text_survives():
    """THE measured contaminant this module exists to handle. Real filings put
    an <ix:header> dump of every tagged fact and its taxonomy URIs ahead of the
    document; live on Apple's FY2025 10-K that was ~14,000 characters of
    'P1Y P1Y http://fasb.org/us-gaap/2025#...' before a single English word.
    Its content varies with how many facts the filer tagged that year, so
    leaving it in manufactures 'language change' unrelated to language."""
    raw = (
        "<html><body>"
        "<ix:header><ix:hidden>P1Y P1Y "
        "http://fasb.org/us-gaap/2025#LongTermDebtNoncurrent</ix:hidden>"
        "<ix:references>0000320193</ix:references></ix:header>"
        "<p>UNITED STATES SECURITIES AND EXCHANGE COMMISSION</p>"
        "</body></html>"
    )
    text = html_to_text(raw)
    assert "UNITED STATES SECURITIES AND EXCHANGE COMMISSION" in text
    assert "fasb.org" not in text
    assert "P1Y" not in text


def test_standalone_ix_hidden_block_is_also_removed():
    raw = "<ix:hidden>machine only 0000320193</ix:hidden><p>Real prose here.</p>"
    text = html_to_text(raw)
    assert "machine only" not in text
    assert "Real prose here." in text


def test_script_style_and_comments_are_removed():
    raw = (
        "<style>.a{color:red}</style>"
        "<script>var x = 1;</script>"
        "<!-- a comment -->"
        "<p>Visible prose.</p>"
    )
    text = html_to_text(raw)
    assert text == "Visible prose."


def test_html_entities_are_decoded_and_nbsp_normalized():
    raw = "<p>AT&amp;T&nbsp;reported&#8212;results</p>"
    text = html_to_text(raw)
    assert "AT&T" in text
    assert "\xa0" not in text
    assert "&nbsp;" not in text


def test_block_level_structure_becomes_newlines_and_inline_does_not():
    """Load-bearing, not cosmetic: extract_section's line anchoring depends on
    a real heading occupying its own block element. Inline markup inside a
    sentence must NOT introduce a line break, or a mid-sentence
    cross-reference would look like a heading."""
    raw = "<p>Item 1A. Risk Factors</p><p>Body <b>with</b> <i>inline</i> markup.</p>"
    text = html_to_text(raw)
    assert "Item 1A. Risk Factors\nBody" in text
    assert "Body with inline markup." in text


def test_html_to_text_collapses_runs_of_whitespace_but_keeps_single_newlines():
    raw = "<p>alpha     beta</p>\n\n\n<p>gamma</p>"
    assert html_to_text(raw) == "alpha beta\ngamma"


# --- extract_section: the wrong-content defect this guards against ---------


def _doc_with_section(body_words: int = 300) -> str:
    return (
        _padding()
        + "<p>Item 1A. Risk Factors</p>"
        + "<p>" + ("risk body " * body_words) + "</p>"
        + "<p>Item 1B. Unresolved Staff Comments</p>"
        + _padding()
    )


def test_line_anchored_heading_extracts_the_real_section_body():
    text = html_to_text(_doc_with_section())
    section = extract_section(text, "risk_factors")
    assert section is not None
    assert "risk body" in section
    assert "other filing content" not in section


def test_mid_sentence_cross_reference_is_not_treated_as_a_heading():
    """THE defect that a size guard could not catch and only a content check
    did. Matching heading words anywhere in flattened text made Apple's
    'risk_factors' begin inside the forward-looking-statements disclaimer,
    reached through a cross-reference. A cross-reference sits mid-sentence; a
    real heading starts a line."""
    raw = (
        "<p>As described in Item 1A. Risk Factors of this report, we face many risks.</p>"
        + _padding()
        + "<p>Item 1B. Unresolved Staff Comments</p>"
    )
    assert extract_section(html_to_text(raw), "risk_factors") is None


def test_table_of_contents_entry_alone_does_not_produce_a_section():
    """A TOC lists 'Item 1A' immediately followed by 'Item 1B', so pairing each
    start with the FIRST following terminator yields a span far under
    MIN_SECTION_CHARS, which is dropped."""
    raw = (
        "<p>Item 1A. Risk Factors</p>"
        "<p>Item 1B. Unresolved Staff Comments</p>"
        + _padding()
    )
    assert extract_section(html_to_text(raw), "risk_factors") is None


def test_span_larger_than_half_the_document_is_refused():
    """The other measured silent failure: an early stray marker pairing with a
    late terminator returned 87-98% of the whole document for GE and Exxon —
    the document wearing a section's name. Rejected, not returned."""
    raw = (
        "<p>Item 1A. Risk Factors</p>"
        + "<p>" + ("huge body " * 5000) + "</p>"
        + "<p>Item 1B. Unresolved Staff Comments</p>"
        + "<p>tiny tail</p>"
    )
    text = html_to_text(raw)
    section = extract_section(text, "risk_factors")
    assert section is None or len(section) <= len(text) * MAX_SECTION_DOC_FRACTION


def test_section_shorter_than_the_floor_is_refused():
    raw = (
        _padding()
        + "<p>Item 1A. Risk Factors</p><p>too short</p>"
        + "<p>Item 1B. Unresolved Staff Comments</p>"
        + _padding()
    )
    assert extract_section(html_to_text(raw), "risk_factors") is None
    assert MIN_SECTION_CHARS == 1_000


def test_missing_terminator_yields_none_rather_than_running_to_end_of_document():
    raw = _padding() + "<p>Item 1A. Risk Factors</p><p>" + ("risk body " * 300) + "</p>"
    assert extract_section(html_to_text(raw), "risk_factors") is None


def test_mda_section_extracts_with_item_7_heading():
    raw = (
        _padding()
        + "<p>Item 7. Management's Discussion and Analysis of Financial Condition</p>"
        + "<p>" + ("discussion body " * 300) + "</p>"
        + "<p>Item 7A. Quantitative and Qualitative Disclosures About Market Risk</p>"
        + _padding()
    )
    section = extract_section(html_to_text(raw), "mda")
    assert section is not None
    assert "discussion body" in section


def test_item_2_properties_also_terminates_risk_factors():
    """Real filings vary: some go 1A -> 1B -> 2, some 1A -> 2 directly."""
    raw = (
        _padding()
        + "<p>Item 1A. Risk Factors</p>"
        + "<p>" + ("risk body " * 300) + "</p>"
        + "<p>Item 2. Properties</p>"
        + _padding()
    )
    section = extract_section(html_to_text(raw), "risk_factors")
    assert section is not None and "risk body" in section


def test_unknown_section_name_raises_rather_than_returning_none():
    """A typo'd scope must be a loud failure, not a silent 'this filing has no
    such section' that would quietly empty a whole panel."""
    with pytest.raises(ValueError, match="unknown section"):
        extract_section("some text", "executive_compensation")


def test_extraction_failure_is_none_not_empty_string():
    """None means 'could not locate'. An empty string would tokenize to zero
    terms and score as maximally CHANGED, putting every parse failure straight
    into the short leg."""
    assert extract_section("nothing resembling a filing", "risk_factors") is None


# --- availability_date: the point-in-time rule ------------------------------


def test_acceptance_before_four_pm_eastern_is_available_the_same_day():
    filing = _filing(acceptance="2025-10-31T10:01:26.000Z")  # 06:01 ET
    assert availability_date(filing) == date(2025, 10, 31)


def test_acceptance_after_four_pm_eastern_moves_to_the_next_day():
    """Real recorded case: Apple's FY2023 10-K was accepted 2023-11-02T22:08:27Z
    = 18:08 ET, and EDGAR's own filingDate for it is 2023-11-03."""
    filing = _filing(acceptance="2023-11-02T22:08:27.000Z", filing_date=date(2023, 11, 3))
    assert availability_date(filing) == date(2023, 11, 3)


def test_exactly_four_pm_eastern_counts_as_after_close():
    filing = _filing(acceptance="2025-10-31T20:00:00.000Z")  # 16:00 ET exactly
    assert availability_date(filing) == date(2025, 11, 1)


def test_tz_naive_acceptance_is_read_as_utc_not_machine_local_time():
    """The exact latent bug an adversarial pass found in
    cross_sectional_pead.announcement_day0 on 2026-08-28: datetime.astimezone()
    on a naive value silently assumes the HOST machine's timezone, shifting
    availability by a day differently on different machines with no error."""
    naive = _filing(acceptance="2025-10-31T10:01:26")
    aware = _filing(acceptance="2025-10-31T10:01:26+00:00")
    assert availability_date(naive) == availability_date(aware) == date(2025, 10, 31)


def test_missing_acceptance_falls_back_to_the_day_after_filing():
    filing = _filing(acceptance="", filing_date=date(2025, 10, 31))
    assert availability_date(filing) == date(2025, 11, 1)


def test_unparseable_acceptance_falls_back_conservatively():
    filing = _filing(acceptance="not-a-timestamp", filing_date=date(2025, 10, 31))
    assert availability_date(filing) == date(2025, 11, 1)


def test_availability_never_depends_on_the_fiscal_period_end():
    """THE look-ahead guard. Measured on 481 real 10-Ks, availability_date minus
    report_date has median 53 days and maximum 107 — keying the signal to the
    period end would read language that did not exist for ~2 months. Two
    filings identical except for wildly different report_dates (including None)
    must produce the SAME availability date."""
    base = _filing(report_date=date(2025, 9, 27))
    far_earlier = _filing(report_date=date(2019, 1, 1))
    absent = _filing(report_date=None)
    assert (
        availability_date(base)
        == availability_date(far_earlier)
        == availability_date(absent)
        == date(2025, 10, 31)
    )


def test_availability_is_never_earlier_than_the_period_end_on_real_shaped_input():
    filing = _filing()
    assert filing.report_date is not None
    assert availability_date(filing) > filing.report_date


# --- parse_filing_rows: the recorded submissions shape ----------------------


def test_parse_filing_rows_matches_the_verified_submissions_shape():
    payload = _submissions(
        [
            _row(
                "0000320193-25-000079",
                "10-K",
                "2025-10-31",
                report="2025-09-27",
                acceptance="2025-10-31T10:01:26.000Z",
                primary="aapl-20250927.htm",
            )
        ]
    )
    filings = parse_filing_rows(320193, payload)
    assert len(filings) == 1
    f = filings[0]
    assert f.cik == 320193
    assert f.form == "10-K"
    assert f.filing_date == date(2025, 10, 31)
    assert f.report_date == date(2025, 9, 27)
    assert f.primary_document == "aapl-20250927.htm"


def test_amendments_are_excluded_not_mapped_onto_their_base_form():
    """A 10-K/A is usually a partial re-filing of one item or an exhibit.
    Treating it as a full annual report would manufacture an enormous spurious
    language change for whichever firm filed one."""
    payload = _submissions(
        [
            _row("a", "10-K", "2024-02-01"),
            _row("b", "10-K/A", "2024-03-01"),
            _row("c", "10-Q/A", "2024-05-01"),
        ]
    )
    forms = {f.form for f in parse_filing_rows(320193, payload)}
    assert forms == {"10-K"}


def test_rows_without_a_primary_document_are_skipped():
    payload = _submissions(
        [_row("a", "10-K", "2024-02-01", primary=""), _row("b", "10-K", "2023-02-01")]
    )
    assert [f.accession for f in parse_filing_rows(320193, payload)] == ["b"]


def test_rows_with_an_unparseable_filing_date_are_skipped():
    payload = _submissions(
        [_row("a", "10-K", "not-a-date"), _row("b", "10-K", "2023-02-01")]
    )
    assert [f.accession for f in parse_filing_rows(320193, payload)] == ["b"]


def test_an_unparseable_report_date_leaves_report_date_none_without_dropping_the_row():
    payload = _submissions([_row("a", "10-K", "2024-02-01", report="0000-00-00")])
    filings = parse_filing_rows(320193, payload)
    assert len(filings) == 1 and filings[0].report_date is None


def test_parse_filing_rows_reads_the_flat_older_page_shape():
    """filings.files pages are the SAME parallel arrays at the TOP level, not
    nested under filings.recent — verified live against GE's
    CIK0000040545-submissions-001.json."""
    older = {
        "accessionNumber": ["x"],
        "filingDate": ["2012-02-24"],
        "reportDate": ["2011-12-31"],
        "acceptanceDateTime": ["2012-02-24T12:00:00.000Z"],
        "form": ["10-K"],
        "primaryDocument": ["ge2011.htm"],
    }
    filings = parse_filing_rows(40545, older)
    assert len(filings) == 1 and filings[0].filing_date == date(2012, 2, 24)


def test_only_the_requested_forms_are_returned():
    payload = _submissions(
        [_row("a", "10-K", "2024-02-01"), _row("b", "10-Q", "2024-05-01")]
    )
    assert {f.form for f in parse_filing_rows(320193, payload, forms=("10-Q",))} == {"10-Q"}


# --- provider fetch paths (MockTransport, never the network) ---------------


def _provider(handler, **kwargs) -> EdgarFilingTextProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    kwargs.setdefault("cache_dir", None)
    kwargs.setdefault("sleep", lambda _s: None)
    return EdgarFilingTextProvider(client=client, **kwargs)


def test_list_filings_walks_the_paginated_older_history():
    """Deliberately unlike cross_sectional_pead, which reads filings.recent
    only. A language-change family compares each filing to its OWN
    predecessor, so a truncated window destroys the first usable observation
    of every affected firm rather than merely shortening the sample."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("CIK0000040545.json"):
            return httpx.Response(
                200,
                json=_submissions(
                    [_row("new", "10-K", "2020-02-01")],
                    files=[{"name": "CIK0000040545-submissions-001.json"}],
                ),
            )
        return httpx.Response(
            200,
            json={
                "accessionNumber": ["old"],
                "filingDate": ["2012-02-24"],
                "reportDate": ["2011-12-31"],
                "acceptanceDateTime": ["2012-02-24T12:00:00.000Z"],
                "form": ["10-K"],
                "primaryDocument": ["ge.htm"],
            },
        )

    filings, n_pages = _provider(handler).list_filings(40545)
    assert n_pages == 1
    assert [f.accession for f in filings] == ["old", "new"]


def test_older_pages_can_be_skipped():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "submissions-001" not in str(request.url)
        return httpx.Response(
            200,
            json=_submissions(
                [_row("new", "10-K", "2020-02-01")],
                files=[{"name": "CIK0000040545-submissions-001.json"}],
            ),
        )

    filings, n_pages = _provider(handler).list_filings(40545, include_older_pages=False)
    assert n_pages == 0 and len(filings) == 1


def test_duplicate_accessions_across_pages_are_deduplicated():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("CIK0000040545.json"):
            return httpx.Response(
                200,
                json=_submissions(
                    [_row("dup", "10-K", "2020-02-01")],
                    files=[{"name": "page1.json"}],
                ),
            )
        return httpx.Response(
            200,
            json={
                "accessionNumber": ["dup"],
                "filingDate": ["2020-02-01"],
                "reportDate": [""],
                "acceptanceDateTime": [""],
                "form": ["10-K"],
                "primaryDocument": ["x.htm"],
            },
        )

    filings, _ = _provider(handler).list_filings(40545)
    assert len(filings) == 1


def test_a_failed_older_page_does_not_fail_the_whole_company():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("CIK0000040545.json"):
            return httpx.Response(
                200,
                json=_submissions(
                    [_row("new", "10-K", "2020-02-01")], files=[{"name": "page1.json"}]
                ),
            )
        return httpx.Response(404)

    filings, n_pages = _provider(handler).list_filings(40545)
    assert n_pages == 0 and [f.accession for f in filings] == ["new"]


def test_get_filing_text_converts_the_primary_document_to_text():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm" in str(
            request.url
        )
        return httpx.Response(200, text="<ix:header>junk</ix:header><p>Real prose.</p>")

    assert _provider(handler).get_filing_text(_filing()) == "Real prose."


def test_a_404_document_raises_immediately_without_retrying():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    with pytest.raises(EdgarFetchError):
        _provider(handler).get_filing_text(_filing())
    assert calls["n"] == 1, "a 404 is a real answer, not a transient failure to retry"


def test_a_transient_failure_is_retried_and_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, text="<p>Recovered.</p>")

    assert _provider(handler).get_filing_text(_filing()) == "Recovered."
    assert calls["n"] == 2


def test_persistent_failure_raises_after_the_declared_attempts():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(EdgarFetchError, match="failed after"):
        _provider(handler).get_filing_text(_filing())


def test_the_throttle_spaces_requests_without_real_sleeping():
    slept: list[float] = []
    now = {"t": 0.0}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<p>x</p>")

    provider = _provider(
        handler,
        sleep=slept.append,
        clock=lambda: now["t"],
        min_request_interval=0.13,
    )
    provider.get_filing_text(_filing(accession="a"))
    provider.get_filing_text(_filing(accession="b"))
    assert slept and slept[-1] == pytest.approx(0.13)


def test_the_user_agent_declares_a_contact_as_sec_fair_access_requires():
    provider = EdgarFilingTextProvider(cache_dir=None)
    ua = provider._client.headers["User-Agent"]
    assert "@" in ua, "www.sec.gov 403s any User-Agent without an email-shaped token"
    assert provider._client.headers["Accept-Encoding"] == "gzip, deflate"


# --- caching ---------------------------------------------------------------


def test_filing_text_is_cached_and_the_second_read_does_not_refetch(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, text="<p>Cached prose.</p>")

    provider = _provider(handler, cache_dir=tmp_path)
    first = provider.get_filing_text(_filing())
    second = provider.get_filing_text(_filing())
    assert first == second == "Cached prose."
    assert calls["n"] == 1
    assert provider.n_documents_fetched == 1
    assert provider.n_documents_from_cache == 1


def test_a_corrupt_cache_file_is_refetched_rather_than_raising(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<p>Fresh.</p>")

    provider = _provider(handler, cache_dir=tmp_path)
    provider.get_filing_text(_filing())
    cache_file = next(tmp_path.rglob("*.txt.gz"))
    cache_file.write_bytes(b"not gzip at all")
    assert provider.get_filing_text(_filing()) == "Fresh."


def test_filing_index_round_trips_through_disk(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_submissions([_row("a", "10-K", "2024-02-01")]))

    provider = _provider(handler)
    filings, _pages = provider.list_filings(320193, include_older_pages=False)
    from app.services.market_data.edgar_filing_text_provider import FilingIndexReport

    report = FilingIndexReport(n_tickers_requested=1, n_filings_listed=len(filings))
    path = tmp_path / "index.json"
    save_filing_index({"AAPL": filings}, report, path)
    loaded_index, loaded_report = load_filing_index(path)
    assert loaded_index["AAPL"] == filings
    assert loaded_report.n_filings_listed == len(filings)


def test_load_filing_index_returns_none_when_absent(tmp_path):
    assert load_filing_index(tmp_path / "nope.json") is None


# --- build_filing_index reporting ------------------------------------------


def test_unresolved_and_failed_tickers_are_reported_not_logged_away():
    """Both lists are part of the RESULT, per this project's universe-accounting
    discipline: a consuming family must be able to disclose them."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "company_tickers" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple"},
                    "1": {"cik_str": 40545, "ticker": "GE", "title": "GE"},
                },
            )
        if "CIK0000040545" in str(request.url):
            return httpx.Response(500)
        return httpx.Response(200, json=_submissions([_row("a", "10-K", "2024-02-01")]))

    index, report = _provider(handler).build_filing_index(["AAPL", "GE", "NOPE"])
    assert report.unresolved_tickers == ["NOPE"]
    assert report.failed_tickers == ["GE"]
    assert report.n_tickers_cik_resolved == 2
    assert report.n_tickers_indexed == 1
    assert set(index) == {"AAPL"}


def test_the_ticker_cik_map_uses_this_projects_dash_symbology():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"0": {"cik_str": 1067983, "ticker": "BRK-B", "title": "Berkshire"}}
        )

    assert _provider(handler).get_ticker_cik_map() == {"BRK-B": 1067983}
