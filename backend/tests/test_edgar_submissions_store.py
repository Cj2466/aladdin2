"""Tests for the point-in-time EDGAR submissions store.

The load-bearing one is
test_a_filing_dropped_from_the_endpoint_is_still_served: SEC caps
filings.recent at ~1,000 rows, so an active filer's early 8-Ks leave the
endpoint permanently and a refetch cannot recover them. Retaining them is
the reason this module exists, not a caching side effect.
"""

import gzip
import json
from datetime import date

from app.services.market_data.edgar_submissions_store import (
    DEFAULT_STORE_DIR,
    SHARED_STORE_ROOT,
    EdgarSubmissionsStore,
    EdgarSubmissionsStoreReport,
    flatten_submissions,
    rebuild_submissions,
    store_manifest,
)
from app.services.research_lab.cross_sectional_pead import _parse_item_202_rows

# --- fixtures ---------------------------------------------------------------


def submissions(rows: list[dict], *, cik: int = 320193, name: str = "APPLE INC") -> dict:
    """SEC's own nested shape: filings.recent as parallel arrays."""
    fields = ("accessionNumber", "filingDate", "form", "items", "acceptanceDateTime")
    return {
        "cik": cik,
        "entityName": name,
        "tickers": ["AAPL"],
        "filings": {"recent": {f: [r.get(f) for r in rows] for f in fields}, "files": []},
    }


def filing(accession: str, filed: str, *, form: str = "8-K", items: str = "2.02,9.01") -> dict:
    return {
        "accessionNumber": accession,
        "filingDate": filed,
        "form": form,
        "items": items,
        "acceptanceDateTime": f"{filed}T16:05:00.000Z",
    }


OLD = filing("0000320193-19-000001", "2019-01-29")
MID = filing("0000320193-22-000002", "2022-01-27")
NEW = filing("0000320193-26-000003", "2026-01-28")


# --- round trip and shape ---------------------------------------------------


def test_the_document_round_trips_into_the_shape_pead_parses(tmp_path):
    store = EdgarSubmissionsStore(tmp_path)
    store.merge_submissions(320193, submissions([NEW, MID, OLD]), EdgarSubmissionsStoreReport(),
                            first_seen=date(2026, 9, 10))
    served = store.submissions_as_of(320193)

    events, truncated = _parse_item_202_rows("AAPL", 320193, served, date(2018, 1, 1), date(2026, 12, 31))
    assert [e.accession for e in events] == [
        "0000320193-26-000003",
        "0000320193-22-000002",
        "0000320193-19-000001",
    ]
    assert [str(e.filing_date) for e in events] == ["2026-01-28", "2022-01-27", "2019-01-29"]
    assert truncated is False
    assert "seen" not in json.dumps(served), "the store's own column must not leak into a served document"


def test_rebuild_preserves_every_field_sec_publishes():
    rows = flatten_submissions(submissions([NEW]), first_seen=date(2026, 9, 10))
    rebuilt = rebuild_submissions(320193, "APPLE INC", ["AAPL"], rows)
    recent = rebuilt["filings"]["recent"]
    assert recent["accessionNumber"] == ["0000320193-26-000003"]
    assert recent["items"] == ["2.02,9.01"]
    assert recent["acceptanceDateTime"] == ["2026-01-28T16:05:00.000Z"]
    assert rebuilt["tickers"] == ["AAPL"]
    # fields SEC did not send are present as None, not missing
    assert recent["primaryDocument"] == [None]


def test_a_row_without_an_accession_or_filing_date_cannot_be_dated_and_is_dropped():
    doc = submissions([NEW])
    doc["filings"]["recent"]["accessionNumber"] = [None]
    assert flatten_submissions(doc, first_seen=date(2026, 9, 10)) == []
    doc2 = submissions([NEW])
    doc2["filings"]["recent"]["filingDate"] = [None]
    assert flatten_submissions(doc2, first_seen=date(2026, 9, 10)) == []


def test_a_ragged_response_does_not_fail_the_ingest():
    """A short array yields None for the missing rows rather than raising —
    the same policy the price provider keeps for a ragged vendor batch."""
    doc = submissions([NEW, MID])
    doc["filings"]["recent"]["items"] = ["2.02"]  # one element for two filings
    rows = flatten_submissions(doc, first_seen=date(2026, 9, 10))
    assert len(rows) == 2
    assert {r["items"] for r in rows} == {"2.02", None}


def test_an_empty_or_malformed_document_yields_no_rows():
    assert flatten_submissions({}, first_seen=date(2026, 9, 10)) == []
    assert flatten_submissions({"filings": {"recent": []}}, first_seen=date(2026, 9, 10)) == []
    assert flatten_submissions({"filings": {"recent": {}}}, first_seen=date(2026, 9, 10)) == []


# --- THE point: retention ---------------------------------------------------


def test_a_filing_dropped_from_the_endpoint_is_still_served(tmp_path):
    """SEC caps filings.recent at ~1,000 rows. For an active filer the window
    slides forward and old 8-Ks leave the endpoint permanently — this family's
    own 2026-08-28 run found 181 of 503 tickers already truncated. Once stored,
    a row must never leave."""
    store = EdgarSubmissionsStore(tmp_path)
    store.merge_submissions(320193, submissions([MID, OLD]), EdgarSubmissionsStoreReport(),
                            first_seen=date(2022, 2, 1))
    # a later fetch: SEC has dropped the 2019 filing and added a 2026 one
    report = EdgarSubmissionsStoreReport()
    n_new = store.merge_submissions(320193, submissions([NEW, MID]), report, first_seen=date(2026, 9, 10))

    assert n_new == 1
    served = store.submissions_as_of(320193)
    events, _ = _parse_item_202_rows("AAPL", 320193, served, date(2018, 1, 1), date(2026, 12, 31))
    assert [e.accession for e in events] == [
        "0000320193-26-000003",
        "0000320193-22-000002",
        "0000320193-19-000001",
    ], "the dropped 2019 filing is still there"
    assert store.earliest_filing_date(320193) == date(2019, 1, 29)


def test_first_write_wins_and_a_changed_row_is_reported(tmp_path):
    store = EdgarSubmissionsStore(tmp_path)
    store.merge_submissions(320193, submissions([NEW]), EdgarSubmissionsStoreReport(),
                            first_seen=date(2026, 9, 10))
    mutated = submissions([{**NEW, "items": "8.01", "filingDate": "2026-01-28"}])
    report = EdgarSubmissionsStoreReport()

    assert store.merge_submissions(320193, mutated, report, first_seen=date(2026, 9, 11)) == 0
    assert report.rows_already_present == 1
    assert len(report.revisions) == 1
    cik, accession, filed, stored, incoming = report.revisions[0]
    assert (cik, accession, filed) == (320193, "0000320193-26-000003", "2026-01-28")
    assert stored == {"items": "2.02,9.01"} and incoming == {"items": "8.01"}
    assert "FILING REVISIONS held back" in report.describe()
    served = store.submissions_as_of(320193)
    assert served["filings"]["recent"]["items"] == ["2.02,9.01"], "the stored row stands"


def test_re_ingesting_the_same_document_writes_nothing_and_does_not_re_date(tmp_path):
    store = EdgarSubmissionsStore(tmp_path)
    doc = submissions([NEW, MID])
    store.merge_submissions(320193, doc, EdgarSubmissionsStoreReport(), first_seen=date(2026, 9, 10))
    before = (tmp_path / "CIK0000320193.submissions.json.gz").read_bytes()

    report = EdgarSubmissionsStoreReport()
    assert store.merge_submissions(320193, doc, report, first_seen=date(2026, 9, 30)) == 0
    assert report.rows_already_present == 2
    assert (tmp_path / "CIK0000320193.submissions.json.gz").read_bytes() == before
    _name, _tickers, rows = store.read_rows(320193)
    assert {r["seen"] for r in rows} == {"2026-09-10"}


# --- the dated reads --------------------------------------------------------


def test_as_of_hides_filings_made_later(tmp_path):
    store = EdgarSubmissionsStore(tmp_path)
    store.merge_submissions(320193, submissions([NEW, MID, OLD]), EdgarSubmissionsStoreReport(),
                            first_seen=date(2026, 9, 10))
    served = store.submissions_as_of(320193, as_of=date(2023, 1, 1))
    events, _ = _parse_item_202_rows("AAPL", 320193, served, date(2018, 1, 1), date(2026, 12, 31))
    assert [str(e.filing_date) for e in events] == ["2022-01-27", "2019-01-29"]
    assert store.submissions_as_of(320193, as_of=date(2018, 1, 1))["filings"]["recent"]["form"] == []


def test_knowledge_cutoff_reproduces_what_an_earlier_run_read(tmp_path):
    store = EdgarSubmissionsStore(tmp_path)
    store.merge_submissions(320193, submissions([MID]), EdgarSubmissionsStoreReport(),
                            first_seen=date(2026, 9, 4))
    store.merge_submissions(320193, submissions([MID, OLD]), EdgarSubmissionsStoreReport(),
                            first_seen=date(2026, 9, 10))
    as_the_run_saw_it = store.submissions_as_of(320193, knowledge_cutoff=date(2026, 9, 4))
    events, _ = _parse_item_202_rows("AAPL", 320193, as_the_run_saw_it, date(2018, 1, 1), date(2026, 12, 31))
    assert [e.accession for e in events] == ["0000320193-22-000002"]


def test_an_unknown_cik_reads_as_none_never_an_error(tmp_path):
    store = EdgarSubmissionsStore(tmp_path)
    assert store.submissions_as_of(999999) is None
    assert store.read_rows(999999) == ("", [], [])
    assert store.earliest_filing_date(999999) is None


def test_an_unreadable_store_file_degrades_instead_of_failing(tmp_path, caplog):
    store = EdgarSubmissionsStore(tmp_path)
    store.merge_submissions(320193, submissions([NEW]), EdgarSubmissionsStoreReport(),
                            first_seen=date(2026, 9, 10))
    (tmp_path / "CIK0000320193.submissions.json.gz").write_bytes(b"not gzip")
    with caplog.at_level("WARNING"):
        assert store.read_rows(320193) == ("", [], [])
    assert "unreadable" in caplog.text


# --- ledger, routing, persistence ------------------------------------------


def test_the_ledger_records_a_fetch_even_for_a_cik_with_no_filings(tmp_path):
    store = EdgarSubmissionsStore(tmp_path)
    store.record_fetch(1234, on=date(2026, 9, 10))
    store.record_fetch(1234, on=date(2026, 9, 11))
    store.record_fetch(1234, on=date(2026, 9, 10))
    assert store.read_coverage()["1234"] == ["2026-09-10", "2026-09-11"]
    assert store.last_fetched(1234) == date(2026, 9, 11)
    assert store.last_fetched(9999) is None


def test_the_store_is_shared_with_every_worktree():
    from app.config import MAIN_CHECKOUT_BACKEND_DIR

    assert SHARED_STORE_ROOT == MAIN_CHECKOUT_BACKEND_DIR / "data" / "edgar_submissions_store"
    assert DEFAULT_STORE_DIR.name == "v1"


def test_without_a_store_directory_nothing_is_persisted_and_nothing_raises():
    store = EdgarSubmissionsStore(None)
    report = EdgarSubmissionsStoreReport()
    assert store.merge_submissions(320193, submissions([NEW]), report, first_seen=date(2026, 9, 10)) == 0
    assert store.submissions_as_of(320193) is None
    store.record_fetch(320193)
    assert store.read_coverage() == {}


def test_a_stored_file_is_gzipped_json_a_human_can_open(tmp_path):
    store = EdgarSubmissionsStore(tmp_path)
    store.merge_submissions(320193, submissions([NEW, MID]), EdgarSubmissionsStoreReport(),
                            first_seen=date(2026, 9, 10))
    payload = json.loads(gzip.decompress((tmp_path / "CIK0000320193.submissions.json.gz").read_bytes()))
    assert payload["cik"] == 320193
    assert payload["schema"] == "v1"
    assert payload["tickers"] == ["AAPL"]
    assert [r["accessionNumber"] for r in payload["rows"]] == [
        "0000320193-26-000003",
        "0000320193-22-000002",
    ]


def test_the_manifest_summarises_what_the_store_holds(tmp_path):
    store = EdgarSubmissionsStore(tmp_path)
    store.merge_submissions(320193, submissions([NEW, OLD]), EdgarSubmissionsStoreReport(),
                            first_seen=date(2026, 9, 10))
    manifest = store_manifest(tmp_path)
    assert manifest["n_ciks"] == 1
    assert manifest["n_rows"] == 2
    assert manifest["filing_date_range"] == ["2019-01-29", "2026-01-28"]
    assert manifest["first_seen_range"] == ["2026-09-10", "2026-09-10"]
    assert manifest["bytes_on_disk"] > 0
    assert store_manifest(tmp_path / "nothing_here")["n_ciks"] == 0


# --- the pead wiring --------------------------------------------------------


def _patched_fetch(monkeypatch, responses: dict[int, dict], store):
    """fetch_item_202_events with the network replaced: load_cik_map and each
    submissions GET answer from `responses`."""
    from app.services.research_lab import cross_sectional_pead as pead

    monkeypatch.setattr(pead, "load_cik_map", lambda *a, **k: {"AAPL": 320193})

    def fake_get(url, _user_agent):
        for cik, doc in responses.items():
            if f"CIK{cik:010d}" in url:
                return doc
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(pead, "_sec_get_json", fake_get)
    return pead.fetch_item_202_events(
        ["AAPL"], date(2018, 1, 1), date(2026, 12, 31),
        min_request_interval=0.0, submissions_store=store,
    )


def test_pead_reads_through_the_store_and_discloses_what_it_recovered(tmp_path, monkeypatch):
    """The sample grew for a data-retention reason, so the report has to say
    so — it is a sample-construction fact like every other one."""
    store = EdgarSubmissionsStore(tmp_path)
    store.merge_submissions(320193, submissions([MID, OLD]), EdgarSubmissionsStoreReport(),
                            first_seen=date(2022, 2, 1))

    events, report = _patched_fetch(monkeypatch, {320193: submissions([NEW, MID])}, store)

    assert [e.accession for e in events] == [
        "0000320193-26-000003",
        "0000320193-22-000002",
        "0000320193-19-000001",
    ]
    assert report.n_tickers_recovered_from_store == 1
    assert report.n_events_recovered_from_store == 1
    assert report.n_tickers_fetched == 1


def test_pead_with_the_store_disabled_behaves_exactly_as_before(tmp_path, monkeypatch):
    events, report = _patched_fetch(
        monkeypatch, {320193: submissions([NEW, MID])}, EdgarSubmissionsStore(None)
    )
    assert [e.accession for e in events] == ["0000320193-26-000003", "0000320193-22-000002"]
    assert report.n_events_recovered_from_store == 0


def test_a_store_failure_falls_back_to_the_live_response(tmp_path, monkeypatch, caplog):
    store = EdgarSubmissionsStore(tmp_path)

    def boom(*_a, **_k):
        raise RuntimeError("disk on fire")

    store.merge_submissions = boom  # type: ignore[method-assign]
    with caplog.at_level("ERROR"):
        events, report = _patched_fetch(monkeypatch, {320193: submissions([NEW, MID])}, store)
    assert [e.accession for e in events] == ["0000320193-26-000003", "0000320193-22-000002"]
    assert report.n_events_recovered_from_store == 0
    assert "submissions store failed" in caplog.text
