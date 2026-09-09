"""Tests for the point-in-time EDGAR company-facts store.

The load-bearing ones, in order of what they protect:

  * test_the_document_round_trips_through_the_store_unchanged — a rebuilt
    document must be indistinguishable to extract_line_items from the one
    SEC served, or the store has quietly become a different input.
  * test_a_changed_value_under_the_same_accession_is_refused_and_reported —
    first-write-wins, the policy that makes a rerun reproduce.
  * test_a_restatement_is_a_new_fact_not_a_revision — and the policy must
    NOT swallow the ordinary case it looks like.
  * test_as_of_hides_facts_filed_later — the economic point-in-time read.
  * test_the_whole_document_scale_conflict_scan_stops_seeing_the_future —
    the measured look-ahead channel, closed by construction.
"""

import gzip
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.services.market_data.edgar_facts_store import (
    DEFAULT_STORE_DIR,
    SHARED_STORE_ROOT,
    EdgarFactsStore,
    EdgarFactsStoreReport,
    flatten_document,
    rebuild_document,
    store_manifest,
    utc_today,
)
from app.services.market_data.edgar_xbrl_provider import extract_line_items

# --- fixtures ---------------------------------------------------------------


def entry(
    end: str,
    val: float,
    filed: str,
    accn: str,
    *,
    start: str | None = None,
    form: str = "10-K",
    fy: int | None = None,
) -> dict:
    out = {"end": end, "val": val, "accn": accn, "filed": filed, "form": form}
    if start is not None:
        out["start"] = start
    if fy is not None:
        out["fy"] = fy
    return out


def document(tags: dict[str, list[dict]], *, cik: int = 320193, taxonomy: str = "us-gaap") -> dict:
    return {
        "cik": cik,
        "entityName": "Synthetic Corp",
        "facts": {
            taxonomy: {tag: {"label": tag, "units": {"USD": entries}} for tag, entries in tags.items()}
        },
    }


# One company with two fiscal years, each reported by its own 10-K.
TWO_YEARS = document(
    {
        "Assets": [
            entry("2020-12-31", 1000.0, "2021-02-10", "0000320193-21-000001"),
            entry("2021-12-31", 1200.0, "2022-02-10", "0000320193-22-000001"),
        ],
        "Revenues": [
            entry("2020-12-31", 500.0, "2021-02-10", "0000320193-21-000001", start="2020-01-01"),
            entry("2021-12-31", 600.0, "2022-02-10", "0000320193-22-000001", start="2021-01-01"),
        ],
    }
)


# --- round trip -------------------------------------------------------------


def test_the_document_round_trips_through_the_store_unchanged(tmp_path):
    """What comes back out must be what extract_line_items would have read
    from SEC's own JSON — same line items, same values, same filed dates."""
    store = EdgarFactsStore(tmp_path)
    report = EdgarFactsStoreReport()
    store.merge_document(320193, TWO_YEARS, report, first_seen=date(2026, 9, 10))
    rebuilt = store.document_as_of(320193)

    original = extract_line_items(TWO_YEARS)
    served = extract_line_items(rebuilt)
    assert served.items["assets"].keys() == original.items["assets"].keys()
    for end, item in original.items["assets"].items():
        assert served.items["assets"][end].value == item.value
        assert served.items["assets"][end].filed == item.filed
    assert served.items["revenue"][date(2021, 12, 31)].value == 600.0
    # the store's own bookkeeping column must not leak into a served document
    assert "seen" not in json.dumps(rebuilt)


def test_flatten_keeps_every_taxonomy_and_unit_not_just_the_10k_usd_subset():
    doc = {
        "cik": 1,
        "entityName": "X",
        "facts": {
            "us-gaap": {"Assets": {"units": {"USD": [entry("2021-12-31", 1.0, "2022-01-01", "a-1")]}}},
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {"shares": [entry("2021-12-31", 9.0, "2022-01-01", "a-1", form="10-Q")]}
                }
            },
        },
    }
    rows = flatten_document(doc, first_seen=date(2026, 9, 10))
    assert {(r["tx"], r["u"], r["form"]) for r in rows} == {
        ("us-gaap", "USD", "10-K"),
        ("dei", "shares", "10-Q"),
    }


def test_a_fact_without_filed_or_accession_cannot_be_dated_and_is_dropped():
    doc = document({"Assets": [entry("2021-12-31", 1.0, "2022-01-01", "a-1")]})
    doc["facts"]["us-gaap"]["Assets"]["units"]["USD"].extend(
        [
            {"end": "2020-12-31", "val": 2.0, "accn": "a-0"},  # no filed
            {"end": "2019-12-31", "val": 3.0, "filed": "2020-01-01"},  # no accn
        ]
    )
    rows = flatten_document(doc, first_seen=date(2026, 9, 10))
    assert [r["e"] for r in rows] == ["2021-12-31"]


def test_rebuild_is_the_inverse_of_flatten_for_the_fields_sec_publishes():
    rows = flatten_document(TWO_YEARS, first_seen=date(2026, 9, 10))
    rebuilt = rebuild_document(320193, "Synthetic Corp", rows)
    assert rebuilt["cik"] == 320193
    assert rebuilt["entityName"] == "Synthetic Corp"
    revenues = rebuilt["facts"]["us-gaap"]["Revenues"]["units"]["USD"]
    assert {e["start"] for e in revenues} == {"2020-01-01", "2021-01-01"}
    assets = rebuilt["facts"]["us-gaap"]["Assets"]["units"]["USD"]
    assert all("start" not in e for e in assets), "an instant fact must not gain a start"


# --- first-write-wins -------------------------------------------------------


def test_a_changed_value_under_the_same_accession_is_refused_and_reported(tmp_path):
    """One filing cannot report two different values for one tag and period,
    so this is an SEC re-processing or a bug — never an ordinary update. The
    stored value stands and the disagreement becomes visible."""
    store = EdgarFactsStore(tmp_path)
    store.merge_document(320193, TWO_YEARS, EdgarFactsStoreReport(), first_seen=date(2026, 9, 10))

    mutated = json.loads(json.dumps(TWO_YEARS))
    mutated["facts"]["us-gaap"]["Assets"]["units"]["USD"][0]["val"] = 999.0
    report = EdgarFactsStoreReport()
    n_new = store.merge_document(320193, mutated, report, first_seen=date(2026, 9, 11))

    assert n_new == 0
    assert len(report.revisions) == 1
    cik, tag, end, accn, stored, incoming = report.revisions[0]
    assert (cik, tag, end, stored, incoming) == (320193, "Assets", "2020-12-31", 1000.0, 999.0)
    assert accn == "0000320193-21-000001"
    assert "VALUE REVISIONS held back" in report.describe()
    served = store.document_as_of(320193)
    assert extract_line_items(served).items["assets"][date(2020, 12, 31)].value == 1000.0


def test_a_restatement_is_a_new_fact_not_a_revision(tmp_path):
    """Next year's 10-K carries the prior year as a restated comparative,
    under a NEW accession. That is an addition, and extract_annual_tag_series'
    earliest-filed-wins must still return the originally published figure."""
    store = EdgarFactsStore(tmp_path)
    store.merge_document(320193, TWO_YEARS, EdgarFactsStoreReport(), first_seen=date(2026, 9, 10))

    restated = document(
        {
            "Assets": [
                entry("2020-12-31", 1050.0, "2022-02-10", "0000320193-22-000001"),
            ]
        }
    )
    report = EdgarFactsStoreReport()
    n_new = store.merge_document(320193, restated, report, first_seen=date(2026, 9, 11))

    assert n_new == 1
    assert report.revisions == []
    resolved = extract_line_items(store.document_as_of(320193)).items["assets"]
    assert resolved[date(2020, 12, 31)].value == 1000.0, "the original filing still wins"
    assert resolved[date(2020, 12, 31)].filed == date(2021, 2, 10)


def test_re_ingesting_the_same_document_writes_nothing_and_does_not_re_date(tmp_path):
    store = EdgarFactsStore(tmp_path)
    store.merge_document(320193, TWO_YEARS, EdgarFactsStoreReport(), first_seen=date(2026, 9, 10))
    before = (store.store_dir / "CIK0000320193.facts.json.gz").read_bytes()

    report = EdgarFactsStoreReport()
    assert store.merge_document(320193, TWO_YEARS, report, first_seen=date(2026, 9, 30)) == 0
    assert report.facts_already_present == 4
    assert (store.store_dir / "CIK0000320193.facts.json.gz").read_bytes() == before
    _name, rows = store.read_rows(320193)
    assert {r["seen"] for r in rows} == {"2026-09-10"}


# --- the point-in-time reads ------------------------------------------------


def test_as_of_hides_facts_filed_later(tmp_path):
    store = EdgarFactsStore(tmp_path)
    store.merge_document(320193, TWO_YEARS, EdgarFactsStoreReport(), first_seen=date(2026, 9, 10))

    early = store.document_as_of(320193, as_of=date(2021, 6, 30))
    assert set(extract_line_items(early).items["assets"]) == {date(2020, 12, 31)}
    late = store.document_as_of(320193, as_of=date(2022, 6, 30))
    assert set(extract_line_items(late).items["assets"]) == {
        date(2020, 12, 31),
        date(2021, 12, 31),
    }
    assert store.document_as_of(320193, as_of=date(2019, 1, 1))["facts"] == {}


def test_knowledge_cutoff_reproduces_what_a_run_on_that_date_actually_read(tmp_path):
    """SEC's processing lag is real: a fact filed on the 4th can reach the
    store on the 9th. `as_of` alone would then show a rerun of a window
    ending on the 5th something the original run never saw."""
    store = EdgarFactsStore(tmp_path)
    store.merge_document(
        320193,
        document({"Assets": [entry("2020-12-31", 1000.0, "2026-09-01", "a-1")]}),
        EdgarFactsStoreReport(),
        first_seen=date(2026, 9, 4),
    )
    store.merge_document(
        320193,
        document({"Assets": [entry("2021-12-31", 1200.0, "2026-09-04", "a-2")]}),
        EdgarFactsStoreReport(),
        first_seen=date(2026, 9, 9),
    )

    as_of_only = store.document_as_of(320193, as_of=date(2026, 9, 5))
    assert len(extract_line_items(as_of_only).items["assets"]) == 2

    as_the_run_saw_it = store.document_as_of(
        320193, as_of=date(2026, 9, 5), knowledge_cutoff=date(2026, 9, 4)
    )
    assert set(extract_line_items(as_the_run_saw_it).items["assets"]) == {date(2020, 12, 31)}


def test_an_unknown_cik_reads_as_none_never_an_error(tmp_path):
    store = EdgarFactsStore(tmp_path)
    assert store.document_as_of(123456) is None
    assert store.read_rows(123456) == ("", [])


def test_an_unreadable_store_file_degrades_instead_of_failing_the_read(tmp_path, caplog):
    store = EdgarFactsStore(tmp_path)
    store.merge_document(320193, TWO_YEARS, EdgarFactsStoreReport(), first_seen=date(2026, 9, 10))
    (store.store_dir / "CIK0000320193.facts.json.gz").write_bytes(b"not gzip")
    with caplog.at_level("WARNING"):
        assert store.read_rows(320193) == ("", [])
    assert "unreadable" in caplog.text


# --- the look-ahead the dated read closes -----------------------------------


def test_the_whole_document_scale_conflict_scan_stops_seeing_the_future(tmp_path):
    """extract_line_items drops every (tag, period) whose annual values
    disagree by more than the scale ratio, scanning the WHOLE document — so
    a filing made years later can remove a period an earlier backtest would
    have used. Measured over this project's 163 cached documents it costs 3
    observations out of 15,851 at end-2018 and 0 of 26,951 at end-2024:
    small, real, and closed for free by serving a dated document."""
    doc = document(
        {
            "Assets": [
                entry("2020-12-31", 1000.0, "2021-02-10", "a-1"),
                # the same period re-reported four years later in a different
                # scale — the entity-ambiguity case the scan exists to catch
                entry("2020-12-31", 1000.0 * 5000, "2025-02-10", "a-9"),
            ]
        }
    )
    store = EdgarFactsStore(tmp_path)
    store.merge_document(320193, doc, EdgarFactsStoreReport(), first_seen=date(2026, 9, 10))

    today = extract_line_items(store.document_as_of(320193))
    assert date(2020, 12, 31) not in today.items["assets"], "the scan drops the conflict"
    assert today.n_cross_filing_scale_conflicts == 1

    back_then = extract_line_items(store.document_as_of(320193, as_of=date(2022, 1, 1)))
    assert back_then.items["assets"][date(2020, 12, 31)].value == 1000.0
    assert back_then.n_cross_filing_scale_conflicts == 0


# --- coverage ledger --------------------------------------------------------


def test_the_ledger_records_a_fetch_even_when_the_cik_yielded_no_facts(tmp_path):
    """A CIK SEC has no XBRL for is a real answer, and the ledger is what
    stops it being re-asked on every run forever."""
    store = EdgarFactsStore(tmp_path)
    store.record_fetch(1234, on=date(2026, 9, 10))
    assert store.read_rows(1234) == ("", [])
    assert store.last_fetched(1234) == date(2026, 9, 10)
    store.record_fetch(1234, on=date(2026, 9, 11))
    store.record_fetch(1234, on=date(2026, 9, 10))
    assert store.read_coverage()["1234"] == ["2026-09-10", "2026-09-11"]
    assert store.last_fetched(9999) is None


# --- the ticker -> CIK map --------------------------------------------------


def test_the_cik_map_is_snapshotted_only_when_it_changes(tmp_path):
    store = EdgarFactsStore(tmp_path)
    first = {"AAPL": 320193, "XOM": 34088}
    assert store.record_cik_map(first, on=date(2026, 9, 10)) is not None
    assert store.record_cik_map(first, on=date(2026, 9, 11)) is None, "unchanged: no new file"
    changed = {"AAPL": 320193, "XOM": 2115436}
    assert store.record_cik_map(changed, on=date(2026, 9, 12)) is not None
    assert store.latest_cik_map() == (date(2026, 9, 12), changed)


def test_cik_map_as_of_never_returns_a_later_snapshot(tmp_path):
    store = EdgarFactsStore(tmp_path)
    store.record_cik_map({"XOM": 34088}, on=date(2026, 9, 10))
    store.record_cik_map({"XOM": 2115436}, on=date(2026, 9, 12))
    assert store.cik_map_as_of(date(2026, 9, 11)) == {"XOM": 34088}
    assert store.cik_map_as_of(date(2026, 9, 12)) == {"XOM": 2115436}
    assert store.cik_map_as_of(date(2026, 9, 9)) is None


# --- routing, persistence, clock -------------------------------------------


def test_the_store_is_shared_with_every_worktree_like_the_price_store():
    """A per-worktree fundamentals store would reproduce one level up the
    exact defect that made backtests irreproducible across checkouts on
    2026-09-09. Asserted on SHARED_STORE_ROOT because conftest points
    DEFAULT_STORE_DIR at a tmp_path for the suite."""
    from app.config import MAIN_CHECKOUT_BACKEND_DIR

    assert SHARED_STORE_ROOT == MAIN_CHECKOUT_BACKEND_DIR / "data" / "edgar_facts_store"
    assert SHARED_STORE_ROOT.parts[-3:] == ("backend", "data", "edgar_facts_store")
    assert DEFAULT_STORE_DIR.name == "v1"


def test_without_a_store_directory_nothing_is_persisted_and_nothing_raises():
    store = EdgarFactsStore(None)
    report = EdgarFactsStoreReport()
    assert store.merge_document(320193, TWO_YEARS, report, first_seen=date(2026, 9, 10)) == 0
    assert store.document_as_of(320193) is None
    assert store.record_cik_map({"AAPL": 320193}) is None
    store.record_fetch(320193)
    assert store.read_coverage() == {}


def test_utc_today_is_the_utc_date_not_the_local_one():
    assert utc_today() == datetime.now(UTC).date()


def test_the_manifest_summarises_what_the_store_holds(tmp_path):
    store = EdgarFactsStore(tmp_path)
    store.merge_document(320193, TWO_YEARS, EdgarFactsStoreReport(), first_seen=date(2026, 9, 10))
    store.record_cik_map({"AAPL": 320193}, on=date(2026, 9, 10))
    manifest = store_manifest(tmp_path)
    assert manifest["n_ciks"] == 1
    assert manifest["n_facts"] == 4
    assert manifest["filed_range"] == ["2021-02-10", "2022-02-10"]
    assert manifest["first_seen_range"] == ["2026-09-10", "2026-09-10"]
    assert manifest["cik_map_snapshots"] == ["2026-09-10"]
    assert manifest["bytes_on_disk"] > 0


def test_a_stored_file_is_gzipped_json_a_human_can_open(tmp_path):
    """The store is evidence, so it must stay readable without this module."""
    store = EdgarFactsStore(tmp_path)
    store.merge_document(320193, TWO_YEARS, EdgarFactsStoreReport(), first_seen=date(2026, 9, 10))
    payload = json.loads(gzip.decompress((tmp_path / "CIK0000320193.facts.json.gz").read_bytes()))
    assert payload["cik"] == 320193
    assert payload["schema"] == "v1"
    assert len(payload["rows"]) == 4
    assert payload["rows"][0]["seen"] == "2026-09-10"


@pytest.mark.parametrize("cik", [320193, 1, 9999999999])
def test_the_file_name_is_the_ten_digit_padded_cik_sec_uses(tmp_path, cik):
    store = EdgarFactsStore(tmp_path)
    assert store._path(cik) == Path(tmp_path) / f"CIK{cik:010d}.facts.json.gz"


# --- the provider wiring ----------------------------------------------------


def _provider(tmp_path, store):
    """A provider with a populated disk cache and no network path: every
    call it makes here is answered from the cache file."""
    from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider

    cache = tmp_path / "cache"
    cache.mkdir(exist_ok=True)
    (cache / "CIK0000320193.json").write_text(json.dumps(TWO_YEARS))
    return EdgarXbrlProvider(cache_dir=cache, facts_store=store, client=object())


def test_get_company_facts_returns_the_document_verbatim_and_ingests_it(tmp_path):
    """The wiring must be invisible to every existing caller: the returned
    document is the cache file's, byte for byte, and the store fills up on
    the way past."""
    store = EdgarFactsStore(tmp_path / "store")
    provider = _provider(tmp_path, store)

    returned = provider.get_company_facts(320193)
    assert returned == TWO_YEARS
    assert provider.facts_store_report.facts_written == 4
    assert store.last_fetched(320193) == utc_today()
    assert extract_line_items(store.document_as_of(320193)).items["assets"][
        date(2021, 12, 31)
    ].value == 1200.0


def test_a_second_call_on_the_same_utc_day_does_not_re_ingest(tmp_path):
    """Measured cost is 0.05-0.15 s per document and the live runner ticks
    every 1,800 s over ~165 CIKs; re-comparing every tick would burn ~18 s
    each time to learn that nothing changed."""
    store = EdgarFactsStore(tmp_path / "store")
    provider = _provider(tmp_path, store)
    provider.get_company_facts(320193)

    calls = []
    original = store.merge_document
    store.merge_document = lambda *a, **k: (calls.append(a) or original(*a, **k))  # type: ignore[method-assign]
    provider.get_company_facts(320193)
    assert calls == [], "already ingested today"


def test_a_store_failure_never_costs_a_family_its_tick(tmp_path, caplog):
    """The store is evidence, not a dependency of the live path."""
    store = EdgarFactsStore(tmp_path / "store")

    def boom(*_args, **_kwargs):
        raise RuntimeError("disk on fire")

    store.merge_document = boom  # type: ignore[method-assign]
    provider = _provider(tmp_path, store)
    with caplog.at_level("ERROR"):
        assert provider.get_company_facts(320193) == TWO_YEARS
    assert "ingest failed" in caplog.text


def test_get_company_facts_as_of_answers_from_the_store_and_never_fetches(tmp_path):
    store = EdgarFactsStore(tmp_path / "store")
    provider = _provider(tmp_path, store)
    assert provider.get_company_facts_as_of(320193, date(2026, 1, 1)) is None, "nothing stored yet"

    provider.get_company_facts(320193)
    early = provider.get_company_facts_as_of(320193, date(2021, 6, 30))
    assert set(extract_line_items(early).items["assets"]) == {date(2020, 12, 31)}
    assert provider.get_company_facts_as_of(999999, date(2026, 1, 1)) is None


def test_the_ticker_cik_map_is_snapshotted_when_it_is_read(tmp_path):
    from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider

    store = EdgarFactsStore(tmp_path / "store")
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "company_tickers.json").write_text(
        json.dumps({"0": {"cik_str": 320193, "ticker": "AAPL", "title": "APPLE INC"}})
    )
    provider = EdgarXbrlProvider(cache_dir=cache, facts_store=store, client=object())

    assert provider.get_ticker_cik_map() == {"AAPL": 320193}
    assert store.latest_cik_map() == (utc_today(), {"AAPL": 320193})
    assert provider.get_ticker_cik_map_as_of(utc_today()) == {"AAPL": 320193}
    assert provider.get_ticker_cik_map_as_of(date(2020, 1, 1)) is None


def test_a_provider_with_no_store_behaves_exactly_as_before(tmp_path):
    store = EdgarFactsStore(None)
    provider = _provider(tmp_path, store)
    assert provider.get_company_facts(320193) == TWO_YEARS
    assert provider.facts_store_report.facts_written == 0
    assert provider.get_company_facts_as_of(320193, date(2026, 1, 1)) is None
