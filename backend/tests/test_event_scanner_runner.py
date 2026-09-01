"""EventScannerRunner — Stage A scanning, persistence, and per-source failure
containment.

Every external boundary is a scripted fake: no yfinance, no FRED, no GDELT, no
SEC. The three sources' real response shapes are covered by
test_gdelt_provider.py and test_sec_edgar_rss_provider.py; what is exercised
here is the RUNNER's own contract —

  * every tick persists one full-snapshot row per source, trigger or not,
  * each of the three sources can trigger independently of the others,
  * a failing source neither crashes the tick nor blocks the other two,
  * nothing in this phase ever escalates (Stage B does not exist).

Session isolation mirrors test_macro_beta_refresh_runner.py: the runner opens
its own SessionLocal (it is not a FastAPI route, so the get_db override does
not reach it), so that name is pointed at the per-test SQLite engine.
"""

import asyncio
import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.macro_event_detection import MacroEventDetection
from app.services.macro_data.base import MacroObservationResult
from app.services.macro_event import event_scanner_runner as runner_module
from app.services.macro_event.drivers import (
    SOURCE_EDGAR,
    SOURCE_GDELT,
    SOURCE_NUMERIC,
    VOL_INDEX_SYMBOLS,
)
from app.services.macro_event.event_scanner_runner import EventScannerRunner
from app.services.macro_event.gdelt_provider import GdeltSeriesSignal
from app.services.macro_event.sec_edgar_rss_provider import FilingEntry
from app.services.research_lab.macro_beta import DRIVER_SOURCE_ETF, MACRO_DRIVERS

ETF_SYMBOLS = [d.symbol for d in MACRO_DRIVERS if d.source == DRIVER_SOURCE_ETF]
FRED_SYMBOLS = [d.symbol for d in MACRO_DRIVERS if d.source != DRIVER_SOURCE_ETF]
ALL_PRICE_SYMBOLS = [*ETF_SYMBOLS, *VOL_INDEX_SYMBOLS.values()]


@pytest.fixture(autouse=True)
def patch_runner_session(test_db_engine, monkeypatch):
    testing_session_local = sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(runner_module, "SessionLocal", testing_session_local)


# --- scripted fakes at every I/O boundary ----------------------------------


class FakePriceProvider:
    """Returns a flat 2-bar frame by default, so nothing trips. `moves` sets a
    per-symbol second-bar multiplier to drive one symbol over its threshold."""

    def __init__(self, moves: dict[str, float] | None = None, fail: bool = False):
        self.moves = moves or {}
        self.fail = fail

    def get_price_history(self, tickers, start, end):
        if self.fail:
            raise RuntimeError("yfinance exploded")
        index = pd.to_datetime([date(2026, 8, 31), date(2026, 9, 1)])
        data = {t: [100.0, 100.0 * (1.0 + self.moves.get(t, 0.0))] for t in tickers}
        return pd.DataFrame(data, index=index), []


class FakeMacroProvider:
    """FRED returns NEWEST FIRST (sort_order=desc) — the real contract, and
    getting it backwards would silently flip the sign of every rate move."""

    def __init__(self, deltas: dict[str, float] | None = None, fail: bool = False):
        self.deltas = deltas or {}
        self.fail = fail

    def get_latest_observations(self, series_id, fred_units, limit=5):
        if self.fail:
            raise RuntimeError("FRED exploded")
        base = 4.0
        latest = base + self.deltas.get(series_id, 0.0)
        return [
            MacroObservationResult(observation_date=date(2026, 9, 1), value=latest),
            MacroObservationResult(observation_date=date(2026, 8, 31), value=base),
        ]


class FakeGdelt:
    def __init__(self, zscore=0.0, shift=0.0, fail=False):
        self.zscore, self.shift, self.fail = zscore, shift, fail

    def fetch_series(self, theme_key, query, mode, **kwargs):
        if self.fail:
            raise RuntimeError("GDELT timed out")
        return GdeltSeriesSignal(
            theme_key=theme_key,
            mode=mode,
            n_buckets=40,
            latest=1.0,
            latest_at=datetime(2026, 9, 1, tzinfo=UTC),
            baseline_mean=1.0,
            baseline_std=1.0,
            zscore=self.zscore,
            shift=self.shift,
        )


class FakeEdgar:
    def __init__(self, ciks: list[int] | None = None, fail: bool = False):
        self.ciks, self.fail = ciks or [], fail

    def fetch_latest_filings(self, form_type, **kwargs):
        if self.fail:
            raise RuntimeError("SEC timed out")
        return [
            FilingEntry(
                form_type=form_type,
                company_name=f"Co {cik}",
                cik=cik,
                role="Filer",
                accession_number="0001-26-1",
                url="https://sec.gov/x",
                updated_at=datetime(2026, 9, 1, tzinfo=UTC),
                filed_date="2026-09-01",
                item_numbers=("8.01",),
            )
            for cik in self.ciks
        ]


class FakeCikMap:
    def get_ticker_cik_map(self):
        return {"AAPL": 320193, "MSFT": 789019}


def make_runner(
    *,
    moves=None,
    deltas=None,
    price_fail=False,
    macro_fail=False,
    zscore=0.0,
    shift=0.0,
    gdelt_fail=False,
    edgar_ciks=None,
    edgar_fail=False,
) -> EventScannerRunner:
    return EventScannerRunner(
        price_provider=FakePriceProvider(moves, fail=price_fail),
        macro_provider=FakeMacroProvider(deltas, fail=macro_fail),
        gdelt_provider=FakeGdelt(zscore=zscore, shift=shift, fail=gdelt_fail),
        edgar_provider=FakeEdgar(edgar_ciks, fail=edgar_fail),
        cik_map_provider=FakeCikMap(),
        universe=["AAPL", "MSFT"],
    )


def rows_by_source(outcome) -> dict[str, MacroEventDetection]:
    return {r.source: r for r in outcome.rows}


# --- the core contract: a full snapshot every tick, trigger or not ---------


def test_every_tick_persists_one_row_per_source_even_when_nothing_triggers(test_db_engine):
    """The non-triggers ARE the deliverable. Without them the trigger RATE has
    no denominator, and calibrating the thresholds — this phase's entire
    purpose — becomes impossible."""
    outcome = make_runner()._tick()

    assert len(outcome.rows) == 3
    assert {r.source for r in outcome.rows} == {SOURCE_NUMERIC, SOURCE_GDELT, SOURCE_EDGAR}
    assert outcome.n_triggered == 0

    with test_db_engine.connect() as conn:
        persisted = conn.execute(
            select(MacroEventDetection.source, MacroEventDetection.triggered)
        ).all()
    assert len(persisted) == 3
    assert all(triggered == 0 or triggered is False for _s, triggered in persisted)


def test_the_full_snapshot_records_every_subject_not_only_what_tripped():
    """raw_metrics_json must carry every metric read, so a later calibration
    can replay alternative thresholds against real observed history."""
    outcome = make_runner()._tick()
    numeric = rows_by_source(outcome)[SOURCE_NUMERIC]
    snapshot = json.loads(numeric.raw_metrics_json)

    keys = {m["key"] for m in snapshot["metrics"]}
    # 13 Layer-1 drivers + 6 vol indices, all present on a no-trigger tick.
    assert len(snapshot["metrics"]) == 19
    assert {d.driver_id for d in MACRO_DRIVERS} <= keys
    assert set(VOL_INDEX_SYMBOLS) <= keys
    for metric in snapshot["metrics"]:
        assert "value" in metric and "threshold" in metric and "triggered" in metric


def test_every_row_is_persisted_with_a_shared_detected_at(test_db_engine):
    outcome = make_runner()._tick()
    assert len({r.detected_at for r in outcome.rows}) == 1
    with test_db_engine.connect() as conn:
        stamps = conn.execute(select(MacroEventDetection.detected_at)).scalars().all()
    assert len(set(stamps)) == 1


# --- each source triggers independently ------------------------------------


def test_numeric_source_triggers_on_a_price_driver_alone():
    outcome = make_runner(moves={"USO": 0.10})._tick()
    rows = rows_by_source(outcome)
    assert rows[SOURCE_NUMERIC].triggered is True
    assert rows[SOURCE_NUMERIC].driver == "oil_uso"
    assert rows[SOURCE_NUMERIC].trigger_value == pytest.approx(0.10)
    # The other two sources are untouched by a numeric trip.
    assert rows[SOURCE_GDELT].triggered is False
    assert rows[SOURCE_EDGAR].triggered is False


def test_numeric_source_triggers_on_a_rate_driver_in_basis_points():
    """FRED reports these in percent; the move is x100 into basis points,
    matching macro_beta.levels_to_moves. A 0.5pp jump is 50bp, well over the
    15bp DGS10 threshold."""
    outcome = make_runner(deltas={"DGS10": 0.5})._tick()
    numeric = rows_by_source(outcome)[SOURCE_NUMERIC]
    assert numeric.triggered is True
    assert numeric.trigger_value == pytest.approx(50.0)


def test_vol_index_can_trigger():
    outcome = make_runner(moves={"^VIX": 0.35})._tick()
    numeric = rows_by_source(outcome)[SOURCE_NUMERIC]
    assert numeric.triggered is True
    assert numeric.driver == "vix"


def test_gdelt_source_triggers_alone():
    outcome = make_runner(zscore=9.0)._tick()
    rows = rows_by_source(outcome)
    assert rows[SOURCE_GDELT].triggered is True
    assert rows[SOURCE_GDELT].trigger_metric == "article_volume_zscore"
    assert rows[SOURCE_NUMERIC].triggered is False
    assert rows[SOURCE_EDGAR].triggered is False


def test_gdelt_tone_shift_triggers_independently_of_volume():
    outcome = make_runner(shift=-8.0)._tick()
    gdelt = rows_by_source(outcome)[SOURCE_GDELT]
    assert gdelt.triggered is True
    assert gdelt.trigger_metric == "tone_shift"


def test_edgar_source_triggers_alone_on_an_in_universe_filing():
    outcome = make_runner(edgar_ciks=[320193])._tick()
    rows = rows_by_source(outcome)
    assert rows[SOURCE_EDGAR].triggered is True
    assert rows[SOURCE_NUMERIC].triggered is False
    assert rows[SOURCE_GDELT].triggered is False


def test_edgar_ignores_filings_outside_the_universe():
    """The feed is the WHOLE market — thousands of filers. Only companies in
    the point-in-time universe count, and the snapshot keeps the feed total so
    'nothing filed' stays distinguishable from 'nothing we track filed'."""
    outcome = make_runner(edgar_ciks=[999999999])._tick()
    edgar = rows_by_source(outcome)[SOURCE_EDGAR]
    assert edgar.triggered is False
    snapshot = json.loads(edgar.raw_metrics_json)
    assert snapshot["forms"][0]["value"] == 0.0
    assert snapshot["forms"][0]["n_feed_entries"] == 1


# --- per-source failure containment (the fail-closed discipline) -----------


def test_gdelt_failure_neither_crashes_the_tick_nor_blocks_the_other_sources(test_db_engine):
    """GDELT times out routinely (measured: 18-21s handshakes, frequent
    ECONNRESET). Its failure must cost only its own row."""
    outcome = make_runner(gdelt_fail=True, moves={"USO": 0.10}, edgar_ciks=[320193])._tick()
    rows = rows_by_source(outcome)

    assert rows[SOURCE_GDELT].triggered is False
    assert rows[SOURCE_GDELT].error is not None
    assert "GDELT timed out" in rows[SOURCE_GDELT].error
    assert rows[SOURCE_GDELT].trigger_value is None  # not measured, NOT a measured zero

    # The other two were still checked, still evaluated, still triggered.
    assert rows[SOURCE_NUMERIC].triggered is True
    assert rows[SOURCE_EDGAR].triggered is True

    # And the failing source still wrote a row: a silent gap would look
    # identical to "checked, nothing tripped" and bias the observed rate down.
    with test_db_engine.connect() as conn:
        assert len(conn.execute(select(MacroEventDetection.id)).all()) == 3


@pytest.mark.parametrize(
    "kwargs,failed_source",
    [
        ({"price_fail": True}, SOURCE_NUMERIC),
        ({"macro_fail": True}, SOURCE_NUMERIC),
        ({"gdelt_fail": True}, SOURCE_GDELT),
        ({"edgar_fail": True}, SOURCE_EDGAR),
    ],
)
def test_any_single_source_failure_still_yields_three_persisted_rows(
    kwargs, failed_source, test_db_engine
):
    outcome = make_runner(**kwargs)._tick()
    assert len(outcome.rows) == 3
    assert rows_by_source(outcome)[failed_source].error is not None
    with test_db_engine.connect() as conn:
        assert len(conn.execute(select(MacroEventDetection.id)).all()) == 3


def test_all_three_sources_failing_still_persists_three_rows(test_db_engine):
    outcome = make_runner(price_fail=True, gdelt_fail=True, edgar_fail=True)._tick()
    assert len(outcome.rows) == 3
    assert all(r.error is not None for r in outcome.rows)
    assert outcome.n_triggered == 0
    with test_db_engine.connect() as conn:
        assert len(conn.execute(select(MacroEventDetection.id)).all()) == 3


def test_a_partial_gdelt_failure_keeps_the_answers_but_declares_itself_incomplete():
    """One theme failing while others answer must KEEP the answers — and must
    still say, in the row's own indexed columns, that the scan was incomplete.

    CORRECTED DURING INDEPENDENT VERIFICATION (2026-09-02). This test
    previously asserted `gdelt.error is None` on a partial scan, on the stated
    reasoning that marking the row errored "would wrongly discard the themes
    that did answer". It discards nothing — `triggered` and raw_metrics_json
    are untouched either way — and the cost of the old behaviour was real:
    a partially-measured row was byte-identical, in every column an SQL
    calibration can filter on, to a fully-measured clean one.
    """

    class HalfBrokenGdelt(FakeGdelt):
        def fetch_series(self, theme_key, query, mode, **kwargs):
            if theme_key == "energy":
                raise RuntimeError("GDELT timed out")
            return super().fetch_series(theme_key, query, mode, **kwargs)

    runner = make_runner()
    runner._gdelt_provider = HalfBrokenGdelt(zscore=9.0)
    gdelt = rows_by_source(runner._tick())[SOURCE_GDELT]

    # Nothing is discarded: the themes that answered still drive the trigger.
    assert gdelt.triggered is True
    snapshot = json.loads(gdelt.raw_metrics_json)
    assert any(t.get("error") for t in snapshot["themes"])
    assert any(t.get("triggered") for t in snapshot["themes"])

    # But the row does not pretend to be a complete observation.
    assert gdelt.error is not None
    assert "incomplete scan" in gdelt.error
    assert "GDELT timed out" in gdelt.error
    assert snapshot["coverage"] == {
        "n_checks": 10,
        "n_measured": 8,
        "n_skipped_budget": 0,
        "n_failed": 2,
    }


def test_a_fully_measured_scan_is_the_only_thing_that_leaves_error_null():
    """The invariant the calibration query depends on: `error IS NULL` means
    every check ran. A clean tick is the only row that satisfies it."""
    rows = rows_by_source(make_runner()._tick())
    assert rows[SOURCE_GDELT].error is None
    assert rows[SOURCE_EDGAR].error is None
    assert json.loads(rows[SOURCE_GDELT].raw_metrics_json)["coverage"]["n_measured"] == 10
    assert json.loads(rows[SOURCE_EDGAR].raw_metrics_json)["coverage"]["n_measured"] == 6


def test_a_budget_skipped_scan_is_not_reported_as_a_clean_negative():
    """THE BUG THE FIRST REAL TICK ACTUALLY SHIPPED WITH, pinned.

    On the live run of 2026-09-01 18:57 UTC the GDELT row measured exactly ONE
    of its ten checks — one transport failure, eight skipped by the 120s time
    budget — and was persisted `triggered=False, error=NULL`. In every indexed
    column that is a fully-successful, nothing-tripped scan. Counting it as one
    would bias the observed GDELT trigger rate downward by ~90% of a row, which
    is the exact measurement error this phase exists to avoid.
    """
    now = {"t": 0.0}

    class SlowGdelt(FakeGdelt):
        def fetch_series(self, theme_key, query, mode, **kwargs):
            now["t"] += 130.0  # one slow query blows the whole 120s budget
            return super().fetch_series(theme_key, query, mode, **kwargs)

    runner = make_runner()
    runner._gdelt_provider = SlowGdelt()
    runner._clock = lambda: now["t"]
    gdelt = rows_by_source(runner._tick())[SOURCE_GDELT]

    assert gdelt.triggered is False
    assert gdelt.error is not None, (
        "a scan that measured 1 of 10 checks must not be indistinguishable "
        "from a clean, fully-measured non-trigger"
    )
    assert "incomplete scan" in gdelt.error
    assert "time budget" in gdelt.error
    assert json.loads(gdelt.raw_metrics_json)["coverage"] == {
        "n_checks": 10,
        "n_measured": 1,
        "n_skipped_budget": 9,
        "n_failed": 0,
    }


def test_a_wholly_unmeasured_scan_never_reports_a_falsy_error():
    """A second, sharper form of the same bug, also pinned.

    Reachable today by setting event_gdelt_scan_budget_seconds=0 — the obvious
    way an operator would mute a flaky GDELT during the observation window.
    Every check is then skipped, none RAISES, and the original code joined an
    empty error list into the EMPTY STRING: falsy, so every `if row.error`
    check in every consumer read a wholly unmeasured row as a clean one.
    """
    runner = make_runner()
    runner._clock = lambda: 0.0
    with_zero_budget = runner_module.settings.event_gdelt_scan_budget_seconds
    runner_module.settings.event_gdelt_scan_budget_seconds = 0.0
    try:
        gdelt = rows_by_source(runner._tick())[SOURCE_GDELT]
    finally:
        runner_module.settings.event_gdelt_scan_budget_seconds = with_zero_budget

    assert gdelt.error, f"error must be truthy, got {gdelt.error!r}"
    assert "no check was measured" in gdelt.error
    assert json.loads(gdelt.raw_metrics_json)["coverage"]["n_measured"] == 0


def test_a_total_edgar_failure_is_still_distinguishable_from_a_partial_one():
    """The three states stay three, on the EDGAR source too."""

    class HalfBrokenEdgar(FakeEdgar):
        def fetch_latest_filings(self, form_type, **kwargs):
            if form_type == "8-K":
                raise RuntimeError("SEC timed out")
            return super().fetch_latest_filings(form_type, **kwargs)

    runner = make_runner()
    runner._edgar_provider = HalfBrokenEdgar([320193])
    partial = rows_by_source(runner._tick())[SOURCE_EDGAR]
    assert "incomplete scan" in partial.error
    assert partial.triggered is True  # the form types that answered still count

    total = rows_by_source(make_runner(edgar_fail=True)._tick())[SOURCE_EDGAR]
    assert "no check was measured" in total.error


def test_gdelt_scan_stops_at_its_time_budget_and_records_the_skips():
    """MEASURED FAILURE THIS PREVENTS: on 2026-09-02 GDELT degraded to
    near-constant ECONNRESET, and an unbudgeted scan is
    5 themes x 2 modes x 3 attempts x (6s throttle + 90s timeout) — up to ~48
    MINUTES against a 300-SECOND tick. A real live run was killed at 40 minutes.
    Left unbounded, one bad GDELT day starves the healthy numeric and EDGAR
    sources of their own observations and corrupts the trigger-rate denominator
    this phase exists to measure.

    Skipped checks are recorded as NOT MEASURED with a reason, never dropped
    and never as a measured zero."""
    calls = {"n": 0}
    now = {"t": 0.0}

    class SlowGdelt(FakeGdelt):
        def fetch_series(self, theme_key, query, mode, **kwargs):
            calls["n"] += 1
            now["t"] += 60.0  # each query burns a minute of the budget
            return super().fetch_series(theme_key, query, mode, **kwargs)

    runner = make_runner()
    runner._gdelt_provider = SlowGdelt()
    runner._clock = lambda: now["t"]

    gdelt = rows_by_source(runner._tick())[SOURCE_GDELT]
    snapshot = json.loads(gdelt.raw_metrics_json)

    # 120s budget / 60s per query -> only the first two queries are issued,
    # and the remaining 8 of the 10 (5 themes x 2 modes) are recorded as skips.
    assert calls["n"] == 2
    skipped = [t for t in snapshot["themes"] if "budget" in (t.get("error") or "")]
    assert len(skipped) == 8
    assert all(t["value"] is None and t["triggered"] is False for t in skipped)
    # Every theme/mode still appears — the scan is bounded, not truncated.
    assert len(snapshot["themes"]) == 10


def test_a_fast_gdelt_scan_is_not_affected_by_the_budget():
    runner = make_runner(zscore=9.0)
    runner._clock = lambda: 0.0  # no time passes
    snapshot = json.loads(rows_by_source(runner._tick())[SOURCE_GDELT].raw_metrics_json)
    assert not any("budget" in (t.get("error") or "") for t in snapshot["themes"])


# --- Stage B does not exist in this phase ----------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"moves": {"USO": 0.10}}, {"zscore": 9.0}, {"edgar_ciks": [320193]}, {"gdelt_fail": True}],
)
def test_nothing_ever_escalates_in_this_phase(kwargs):
    """`escalated` is a placeholder for Stage B (Phase 2.3), which does not
    exist. Nothing here may set it, in any combination of triggers."""
    assert all(r.escalated is False for r in make_runner(**kwargs)._tick().rows)


# --- unmeasurable subjects are absent, never a fabricated zero -------------


def test_a_symbol_with_no_data_records_none_not_zero():
    class OneBarProvider(FakePriceProvider):
        def get_price_history(self, tickers, start, end):
            # A single bar cannot yield a daily move.
            index = pd.to_datetime([date(2026, 9, 1)])
            return pd.DataFrame({t: [100.0] for t in tickers}, index=index), []

    runner = make_runner()
    runner._price_provider = OneBarProvider()
    snapshot = json.loads(rows_by_source(runner._tick())[SOURCE_NUMERIC].raw_metrics_json)

    oil = next(m for m in snapshot["metrics"] if m["key"] == "oil_uso")
    assert oil["value"] is None  # NOT 0.0 — "not measured" is not "measured flat"
    assert oil["triggered"] is False


def test_ragged_vol_index_availability_is_handled_per_symbol():
    """MEASURED LIVE 2026-09-01: ^VIX/^VVIX/^OVX/^GVZ had a bar that day while
    ^MOVE/^SKEW did not. Each symbol's move must come from its OWN dropna'd
    series, not from differencing two shared frame rows."""

    class RaggedProvider(FakePriceProvider):
        def get_price_history(self, tickers, start, end):
            index = pd.to_datetime([date(2026, 8, 28), date(2026, 8, 31), date(2026, 9, 1)])
            data = {}
            for t in tickers:
                if t in ("^MOVE", "^SKEW"):
                    data[t] = [100.0, 130.0, None]  # newest bar missing
                else:
                    data[t] = [100.0, 100.0, 100.0]
            return pd.DataFrame(data, index=index), []

    runner = make_runner()
    runner._price_provider = RaggedProvider()
    snapshot = json.loads(rows_by_source(runner._tick())[SOURCE_NUMERIC].raw_metrics_json)

    move = next(m for m in snapshot["metrics"] if m["key"] == "move")
    # Its own last two REAL closes are 100 -> 130, a +30% move, correctly found
    # despite the trailing NaN that a frame-row diff would have returned.
    assert move["value"] == pytest.approx(0.30)
    assert move["triggered"] is True


# --- fixes that had no test until independent verification (2026-09-02) -----
#
# Each of the four below was found by MUTATION: the shipped behaviour was
# correct, but reverting it left the whole suite green, so nothing was stopping
# a future edit from silently undoing it.


def test_prices_are_read_from_the_provider_directly_never_through_price_cache(monkeypatch):
    """MUTATION-PINNED. price_cache treats a rolling window as fresh while its
    newest cached bar is within ROLLING_WINDOW_TOLERANCE_DAYS (4) of the
    requested end. For a daily research job that is right; for an event scanner
    it means computing "today's move" off a bar up to FOUR DAYS OLD and never
    noticing the shock it exists to catch.

    Routing the scanner back through that cache still passed every other test
    in this file (the cache would simply miss and delegate to the same fake),
    so this asserts the bypass directly: the cache function is booby-trapped,
    and the provider must be called with a window ending TODAY.
    """
    from app.services.market_data import price_cache

    def must_not_be_called(*_args, **_kwargs):
        raise AssertionError(
            "the event scanner must call the price provider directly — "
            "price_cache would serve a bar up to 4 days stale"
        )

    monkeypatch.setattr(price_cache, "get_price_history_cached", must_not_be_called)

    seen: dict = {}

    class SpyProvider(FakePriceProvider):
        def get_price_history(self, tickers, start, end):
            seen["start"], seen["end"], seen["tickers"] = start, end, list(tickers)
            return super().get_price_history(tickers, start, end)

    runner = make_runner()
    runner._price_provider = SpyProvider()
    numeric = rows_by_source(runner._tick())[SOURCE_NUMERIC]

    assert numeric.error is None
    assert seen["end"] == runner_module.utcnow_naive().date()
    assert set(VOL_INDEX_SYMBOLS.values()) <= set(seen["tickers"])


def test_the_threshold_in_force_is_snapshotted_onto_the_row_not_read_back_live(
    monkeypatch,
):
    """MUTATION-PINNED, and it is the plan's own words: "threshold value
    snapshotted per row so a later constant change never retroactively rewrites
    history". The whole expected outcome of this phase is retuning these
    constants; if a row pointed at a live setting, the first recalibration
    would rewrite what every already-observed row meant.
    """
    default = runner_module.settings.event_trigger_oil_uso_daily_pct
    before = rows_by_source(make_runner(moves={"USO": 0.10})._tick())[SOURCE_NUMERIC]
    assert before.trigger_threshold == pytest.approx(default)

    # An operator retunes the constant after seeing real trigger rates.
    monkeypatch.setattr(runner_module.settings, "event_trigger_oil_uso_daily_pct", 0.09)

    # The already-observed row still means what it meant when it was written...
    assert before.trigger_threshold == pytest.approx(default)
    # ...and a NEW row records the new value, because thresholds are read at
    # call time rather than bound at import.
    after = rows_by_source(make_runner(moves={"USO": 0.10})._tick())[SOURCE_NUMERIC]
    assert after.trigger_threshold == pytest.approx(0.09)


def test_the_headline_trip_is_ranked_by_exceedance_not_by_raw_magnitude():
    """MUTATION-PINNED. The numeric source mixes FRACTIONS (oil, 0.20) with
    BASIS POINTS (DGS10, 20.0) in one candidate list. Ranking on raw magnitude
    would let every rate driver outrank every price driver by construction —
    20.0 > 0.20 always — so `driver` would name the wrong subject on any tick
    where both trip, and the calibration reads that column.

    Oil here is 5.0x its threshold; DGS10 is only 1.3x its own. The larger
    RAW number is DGS10's; the larger real exceedance is oil's.
    """
    outcome = make_runner(moves={"USO": 0.20}, deltas={"DGS10": 0.2})._tick()
    numeric = rows_by_source(outcome)[SOURCE_NUMERIC]

    snapshot = {m["key"]: m for m in json.loads(numeric.raw_metrics_json)["metrics"]}
    assert snapshot["oil_uso"]["triggered"] is True
    assert snapshot["rate_dgs10"]["triggered"] is True
    assert snapshot["rate_dgs10"]["value"] > snapshot["oil_uso"]["value"]  # raw magnitude

    assert numeric.driver == "oil_uso"
    assert numeric.trigger_metric == "daily_pct_change"


@pytest.mark.parametrize(
    "latest,previous",
    [(100.0, 0.0), (float("nan"), 100.0), (100.0, float("nan")), (float("inf"), 100.0)],
)
def test_an_uncomputable_move_is_none_never_a_fabricated_flat(latest, previous):
    """MUTATION-PINNED. `_pct_move` returning 0.0 on an uncomputable input
    would write a measured "flat" into the snapshot where there was no
    measurement at all — the one confusion this whole table is designed to
    prevent, and it survived every other test because the existing
    missing-data test never reaches this function."""
    assert runner_module._pct_move(latest, previous) is None
    assert runner_module._pct_move(110.0, 100.0) == pytest.approx(0.10)


# --- the run loop itself ----------------------------------------------------


async def test_run_loop_ticks_then_sleeps_the_configured_interval(monkeypatch):
    """Drives the real `run` loop rather than reimplementing its scheduling,
    mirroring test_macro_beta_refresh_runner.py's technique."""
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(runner_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await make_runner().run()

    assert slept == [runner_module.settings.event_scan_interval_seconds]


async def test_a_tick_that_raises_outright_is_logged_and_the_loop_survives(monkeypatch):
    """Belt-and-braces above the per-source containment: even an unexpected
    failure in the tick itself must not kill the background task."""
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(runner_module.asyncio, "sleep", fake_sleep)

    runner = make_runner()
    monkeypatch.setattr(runner, "_tick", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(asyncio.CancelledError):
        await runner.run()
    assert len(slept) == 1
