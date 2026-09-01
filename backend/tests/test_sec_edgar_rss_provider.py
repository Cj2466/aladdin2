"""Unit tests for the SEC EDGAR "Latest Filings" Atom feed client.

The fixtures below are recorded-shape reproductions of what
https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent...&output=atom
actually returned when probed LIVE on 2026-09-01 — including the two entries
quoted verbatim in sec_edgar_rss_provider.py's docstring and the real
"No recent filings" empty feed. NO TEST HERE TOUCHES THE NETWORK.
"""

import httpx
import pytest

from app.services.macro_event.sec_edgar_rss_provider import (
    EdgarFeedError,
    SecEdgarRssProvider,
    parse_filings_atom,
)
from app.services.market_data.edgar_xbrl_provider import build_edgar_user_agent

# Verbatim shape of a real 8-K entry (First Eagle, 2026-09-01) plus a real
# 8-K/A, which is what a `type=8-K` query ACTUALLY returns — the upstream
# `type=` parameter is a prefix match.
FEED_8K = b"""<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Latest Filings - Tue, 01 Sep 2026 13:33:46 EDT</title>
<updated>2026-09-01T13:33:46-04:00</updated>
<entry>
<title>8-K - First Eagle Private Credit Fund (0001890107) (Filer)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/1890107/000119312526378072/0001193125-26-378072-index.htm"/>
<summary type="html">
 &lt;b&gt;Filed:&lt;/b&gt; 2026-09-01 &lt;b&gt;AccNo:&lt;/b&gt; 0001193125-26-378072 &lt;b&gt;Size:&lt;/b&gt; 219 KB
&lt;br&gt;Item 8.01: Other Events
&lt;br&gt;Item 9.01: Financial Statements and Exhibits
</summary>
<updated>2026-09-01T13:20:17-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="8-K"/>
<id>urn:tag:sec.gov,2008:accession-number=0001193125-26-378072</id>
</entry>
<entry>
<title>8-K/A - Some Amending Corp (0000123456) (Filer)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/123456/x-index.htm"/>
<summary type="html"> &lt;b&gt;Filed:&lt;/b&gt; 2026-09-01 &lt;b&gt;AccNo:&lt;/b&gt; 0000123456-26-000001 &lt;b&gt;Size:&lt;/b&gt; 12 KB
&lt;br&gt;Item 2.02: Results of Operations and Financial Condition
</summary>
<updated>2026-09-01T12:00:00-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="8-K/A"/>
<id>urn:tag:sec.gov,2008:accession-number=0000123456-26-000001</id>
</entry>
</feed>
"""

# The real empty feed, ~500 bytes, returned live for `type=SC 13D`.
FEED_EMPTY = b"""<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Latest Filings - Tue, 01 Sep 2026 13:36:57 EDT - No recent filings</title>
<link rel="alternate" href="/cgi-bin/browse-edgar?action=getcurrent"/>
<updated>2026-09-01T13:36:57-04:00</updated>
</feed>
"""

# A real SC 13E3 entry — what `type=SC 13` returned live. It is NOT an
# ownership filing, and the `(Subject)` role appears in the same title slot.
FEED_SC13E3 = b"""<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Latest Filings - Tue, 01 Sep 2026 13:36:14 EDT</title>
<entry>
<title>SC 13E3 - Distribution Solutions Group, Inc. (0000703604) (Subject)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/703604/y-index.htm"/>
<summary type="html"> &lt;b&gt;Filed:&lt;/b&gt; 2026-09-01 &lt;b&gt;AccNo:&lt;/b&gt; 0001193125-26-377697 &lt;b&gt;Size:&lt;/b&gt; 22 MB
</summary>
<updated>2026-09-01T09:25:09-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="SC 13E3"/>
<id>urn:tag:sec.gov,2008:accession-number=0001193125-26-377697</id>
</entry>
</feed>
"""


# --- parsing the real shapes ------------------------------------------------


def test_parses_the_real_8k_entry_field_by_field():
    entries = parse_filings_atom(FEED_8K)
    assert len(entries) == 2
    first = entries[0]
    assert first.form_type == "8-K"
    assert first.company_name == "First Eagle Private Credit Fund"
    assert first.cik == 1890107
    assert first.role == "Filer"
    assert first.accession_number == "0001193125-26-378072"
    assert first.url.endswith("0001193125-26-378072-index.htm")
    assert first.filed_date == "2026-09-01"
    # 8-K item numbers carry the materiality signal.
    assert first.item_numbers == ("8.01", "9.01")
    # <updated> keeps its real -04:00 offset; a naive datetime here would
    # silently shift every filing by four hours.
    assert first.updated_at is not None
    assert first.updated_at.utcoffset() is not None
    assert first.updated_at.isoformat() == "2026-09-01T13:20:17-04:00"


def test_empty_feed_is_a_normal_answer_not_an_error():
    """Verified live: `type=SC 13D` returned HTTP 200 and a feed with zero
    entries titled "No recent filings". 13D/G filings are far rarer than the
    getcurrent window, so this is the COMMON case for them. Raising here
    would corrupt the trigger-rate denominator this whole phase exists to
    measure."""
    assert parse_filings_atom(FEED_EMPTY) == []


def test_non_atom_document_raises():
    with pytest.raises(EdgarFeedError, match="Atom <feed> root"):
        parse_filings_atom(b"<html><body>maintenance</body></html>")


def test_unparseable_xml_raises():
    with pytest.raises(EdgarFeedError, match="not parseable XML"):
        parse_filings_atom(b"<feed><entry>")


def test_a_single_unparseable_title_is_skipped_not_fatal():
    broken = FEED_8K.replace(
        b"<title>8-K/A - Some Amending Corp (0000123456) (Filer)</title>",
        b"<title>total gibberish with no cik</title>",
    )
    entries = parse_filings_atom(broken)
    assert [e.cik for e in entries] == [1890107]


def test_company_name_containing_parentheses_still_yields_the_right_cik():
    """EDGAR company names really do contain parentheses. The CIK and role are
    always the LAST two parenthesised groups, which is why the title regex is
    end-anchored rather than greedy from the left."""
    feed = FEED_8K.replace(
        b"First Eagle Private Credit Fund (0001890107) (Filer)",
        b"Acme Corp (Delaware) (0001890107) (Filer)",
    )
    first = parse_filings_atom(feed)[0]
    assert first.cik == 1890107
    assert first.company_name == "Acme Corp (Delaware)"
    assert first.role == "Filer"


def test_subject_role_is_captured():
    """On an ownership filing the SUBJECT is the company whose stock is being
    accumulated — the market-moving name — while the FILER is the investor."""
    entry = parse_filings_atom(FEED_SC13E3)[0]
    assert entry.role == "Subject"
    assert entry.form_type == "SC 13E3"


# --- the provider's exact-match filter (the prefix-match defence) -----------


def _provider(body: bytes, status_code: int = 200) -> SecEdgarRssProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=body)

    return SecEdgarRssProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _s: None,
    )


def test_prefix_matched_other_form_types_are_filtered_out():
    """THE measured upstream surprise: `type=` is a PREFIX match. A live
    `type=8-K` request returned an `8-K/A` among its entries, and `type=SC 13`
    returned ONLY `SC 13E3` filings. Trusting the query parameter would log
    going-private transactions as 13D/G ownership events."""
    assert [e.form_type for e in _provider(FEED_8K).fetch_latest_filings("8-K")] == ["8-K"]
    assert [e.form_type for e in _provider(FEED_8K).fetch_latest_filings("8-K/A")] == ["8-K/A"]


def test_sc13d_query_does_not_admit_sc13e3():
    assert _provider(FEED_SC13E3).fetch_latest_filings("SC 13D") == []


def test_fetch_sends_the_verified_query_parameters_and_a_compliant_user_agent():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        seen["ua"] = request.headers.get("User-Agent")
        return httpx.Response(200, content=FEED_EMPTY)

    provider = SecEdgarRssProvider(
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            headers={"User-Agent": "Aladdin2 Research test@example.com"},
        ),
        sleep=lambda _s: None,
    )
    provider.fetch_latest_filings("SC 13G")
    assert seen["params"]["action"] == "getcurrent"
    assert seen["params"]["type"] == "SC 13G"
    assert seen["params"]["output"] == "atom"
    # SEC's fair-access policy requires a declared, contactable user agent.
    assert "Aladdin2 Research" in seen["ua"]


# --- pins added by independent verification (2026-09-02) --------------------


def test_the_category_term_outranks_the_title_when_the_two_disagree():
    """MUTATION-PINNED. The provider docstring calls <category term> the
    AUTHORITATIVE form type and the title prefix a mere fallback — but on every
    real entry the two agree, so reading the title instead left the whole suite
    green. This is the one fixture where they disagree.

    It matters because the exact-match filter is built on this field: if the
    title won, a `type=SC 13D` watch could admit an entry whose structured form
    type is something else entirely (SC 13E3 going-private transactions being
    the case actually observed live).
    """
    feed = b"""<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
<title>SC 13D - Disagreeing Corp (0000999001) (Subject)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/x-index.htm"/>
<summary type="html"> &lt;b&gt;Filed:&lt;/b&gt; 2026-09-01 &lt;b&gt;AccNo:&lt;/b&gt; 0000999001-26-000001 </summary>
<updated>2026-09-01T09:25:09-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="SC 13E3"/>
<id>urn:tag:sec.gov,2008:accession-number=0000999001-26-000001</id>
</entry>
</feed>
"""
    (entry,) = parse_filings_atom(feed)
    assert entry.form_type == "SC 13E3", "the structured <category term> is authoritative"
    # And so the ownership watch correctly refuses it.
    assert _provider(feed).fetch_latest_filings("SC 13D") == []


def test_the_default_client_declares_a_compliant_user_agent_without_being_given_one():
    """MUTATION-PINNED. SEC's fair-access policy requires a declared,
    contactable User-Agent on EVERY request and blocks the IP of a client that
    omits one. The existing UA test injects its own httpx.Client carrying its
    own header, so it never exercises the provider's own default — deleting the
    header from the real construction path left every test passing.

    This scanner issues ~1,700 EDGAR requests a day once deployed, so an
    undeclared identity is a live blocking risk, not a formality.
    """
    ua = SecEdgarRssProvider()._client.headers.get("User-Agent")
    assert ua, "the default client must send a User-Agent"
    assert ua == build_edgar_user_agent()
    # SEC's published format is a name plus a contact address.
    name, _, contact = ua.rpartition(" ")
    assert name.strip()
    assert "@" in contact and "." in contact.split("@")[-1]


def test_an_explicit_user_agent_still_overrides_the_default():
    provider = SecEdgarRssProvider(user_agent="Someone Else contact@example.org")
    assert provider._client.headers["User-Agent"] == "Someone Else contact@example.org"


def test_transport_failure_retries_then_raises():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503, text="unavailable")

    provider = SecEdgarRssProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _s: None,
    )
    with pytest.raises(EdgarFeedError, match="failed after"):
        provider.fetch_latest_filings("8-K")
    assert attempts["n"] == 3


def test_a_transient_failure_is_recovered_by_retry():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, content=FEED_8K)

    provider = SecEdgarRssProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _s: None,
    )
    assert len(provider.fetch_latest_filings("8-K")) == 1
    assert attempts["n"] == 2
