"""EventScannerRunner — Stage A of "Project 2", Layer 2 (Phase 2.2).

WHAT THIS RUNNER CAN AND CANNOT DO
============================================================================
It reads market data, news volume and SEC filings, compares numbers against
thresholds, and WRITES DATABASE ROWS. That is the complete list.

It calls no LLM (Stage B is Phase 2.3 and does not exist), places no orders
and touches no execution pathway (Phase 2.4, likewise). It cannot spend money.
`escalated` is written False on every row it produces, and
test_event_scanner_runner.py pins that.

WHY EVERY TICK WRITES THREE ROWS EVEN WHEN NOTHING HAPPENS
============================================================================
This phase exists to measure how often a set of admittedly-guessed thresholds
actually fire, so that a human can calibrate them against reality before any
money or LLM spend depends on them. A rate needs a denominator. Recording only
the moments something tripped would leave the trigger RATE permanently
unrecoverable — you would have the numerator and be guessing the rest.

So each tick writes EXACTLY ONE ROW PER SOURCE — numeric, gdelt, edgar —
whether or not anything tripped, each carrying that source's full snapshot in
raw_metrics_json.

FAIL-CLOSED PER SOURCE, NEVER PER TICK
============================================================================
The three sources are scanned INDEPENDENTLY and a failure in one is contained
to its own row. If GDELT times out — which it does routinely; see
gdelt_provider's docstring on measured 18-21s handshakes and frequent
ECONNRESET — the numeric and EDGAR sources are still checked, still evaluated
and still persisted, and GDELT's row is written with `error` populated,
`triggered=False` and no measurement.

That last part is deliberate and matters for honesty: a failed source writes a
row rather than writing nothing. A silent gap would be indistinguishable from
"checked, nothing tripped", which would quietly bias the observed trigger rate
downward — the exact measurement error this phase exists to avoid.

A KNOWN INTERPRETATION CAVEAT, STATED UP FRONT
============================================================================
THE NUMERIC SOURCE MEASURES A DAILY MOVE, BUT TICKS EVERY 5 MINUTES. Once a
driver's completed daily bar exceeds its threshold, EVERY remaining tick that
day re-observes the same move and re-trips. A 4% oil day therefore produces on
the order of 100-280 triggered numeric rows, not one.

This is a property of the design, not a bug, and the raw data is complete and
correct either way. But whoever performs the calibration MUST count DISTINCT
(driver, UTC date) pairs rather than raw triggered rows, or the numeric
source's apparent trigger rate will be inflated by roughly two orders of
magnitude relative to GDELT's and EDGAR's. Writing it here rather than leaving
it to be rediscovered is the point.

PRICE DATA IS FETCHED DIRECTLY, DELIBERATELY BYPASSING price_cache
============================================================================
get_price_history_cached treats a rolling window as fresh when its newest
cached bar is within ROLLING_WINDOW_TOLERANCE_DAYS (4) of the requested end.
That is exactly right for the daily/weekly research jobs it was built for, and
exactly wrong for an event scanner: it would let this runner compute "today's
move" from a bar up to four days old and never notice a shock. So the scanner
calls the provider directly. As a side benefit it also keeps the vol-index
symbols out of the shared price_bars table, which no other consumer expects to
find them in.
"""

import asyncio
import json
import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.macro_event_detection import MacroEventDetection
from app.services.macro_data.base import MacroDataProvider
from app.services.macro_data.fred_provider import FredProvider
from app.services.macro_event.drivers import (
    EDGAR_MIN_IN_UNIVERSE_FILINGS_TO_TRIGGER,
    EDGAR_WATCHED_FORM_TYPES,
    GDELT_THEMES,
    METRIC_DAILY_BPS,
    METRIC_DAILY_PCT,
    METRIC_EDGAR_FILING_COUNT,
    METRIC_GDELT_TONE_SHIFT,
    METRIC_GDELT_VOLUME_Z,
    SOURCE_EDGAR,
    SOURCE_GDELT,
    SOURCE_NUMERIC,
    VOL_INDEX_SYMBOLS,
    build_driver_triggers,
    build_vol_index_triggers,
)
from app.services.macro_event.gdelt_provider import (
    MODE_TIMELINE_TONE,
    MODE_TIMELINE_VOLUME,
    GdeltProvider,
)
from app.services.macro_event.sec_edgar_rss_provider import SecEdgarRssProvider
from app.services.market_data.base import MarketDataProvider
from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.macro_beta import (
    DRIVER_KIND_PRICE,
    DRIVER_SOURCE_ETF,
    MACRO_DRIVERS_BY_ID,
)
from app.services.research_lab.ticker_universe import SCREENING_UNIVERSE
from app.time_utils import utcnow_naive

logger = logging.getLogger(__name__)

# Calendar days of price history to pull. Only the last two usable closes are
# needed, but a long weekend plus a holiday can span four calendar days, and
# some vol indices publish a day behind the others (measured: on 2026-09-01
# ^MOVE and ^SKEW had no bar while ^VIX did), so this is deliberately generous.
PRICE_LOOKBACK_DAYS = 14

# FRED observations to request per series. Only the last two are used; the
# extra headroom absorbs the sentinel "." values FredProvider already drops.
FRED_OBSERVATION_LIMIT = 5


@dataclass
class EventScanTickOutcome:
    """One tick's result. `rows` is always len(ALL_SOURCES) — three."""

    detected_at: datetime
    rows: list[MacroEventDetection]

    @property
    def n_triggered(self) -> int:
        return sum(1 for r in self.rows if r.triggered)


def _pct_move(latest: float, previous: float) -> float | None:
    """Simple daily return. None when the base is zero or either side is
    non-finite — never a fabricated 0.0, which would read as a measured
    'flat' rather than as the absence of a measurement."""
    if previous == 0 or not (math.isfinite(latest) and math.isfinite(previous)):
        return None
    return latest / previous - 1.0


def _headline(candidates: list[dict]) -> dict | None:
    """The most significant trip among a source's subjects: the largest
    exceedance RELATIVE TO ITS OWN THRESHOLD.

    Ranking on the raw value instead would be meaningless — the numeric source
    mixes fractions (0.04) with basis points (15.0), so a raw-magnitude
    comparison would let every rate driver outrank every price driver by
    construction. The ratio is unit-free and therefore comparable.
    """
    tripped = [c for c in candidates if c.get("triggered")]
    if not tripped:
        return None
    return max(tripped, key=lambda c: abs(c["value"]) / c["threshold"] if c["threshold"] else 0.0)


class EventScannerRunner:
    """Standard `while True: tick(); sleep()` background runner, launched
    alongside the other runners in main.py's lifespan.

    Every collaborator is injectable so tests drive the whole tick with
    scripted fakes and no network — the same contract
    test_execution_runner.py's scripted broker fake keeps.
    """

    def __init__(
        self,
        price_provider: MarketDataProvider | None = None,
        macro_provider: MacroDataProvider | None = None,
        gdelt_provider: GdeltProvider | None = None,
        edgar_provider: SecEdgarRssProvider | None = None,
        cik_map_provider: EdgarXbrlProvider | None = None,
        universe: list[str] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        # Injectable so a test can drive the GDELT time budget deterministically
        # without real waiting. Monotonic, not wall-clock: a budget must not be
        # broken by an NTP step mid-tick.
        self._clock = clock
        self._price_provider = price_provider
        self._macro_provider = macro_provider
        self._gdelt_provider = gdelt_provider
        self._edgar_provider = edgar_provider
        self._cik_map_provider = cik_map_provider
        self._universe = universe
        # Resolved once and reused: EdgarXbrlProvider disk-caches SEC's
        # company_tickers.json, so this is one fetch per process at most.
        self._universe_ciks: set[int] | None = None

    async def run(self) -> None:
        while True:
            try:
                outcome = await asyncio.to_thread(self._tick)
                logger.info(
                    "macro event scan: %d/%d sources triggered at %s",
                    outcome.n_triggered,
                    len(outcome.rows),
                    outcome.detected_at.isoformat(),
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Macro event scan tick failed; will retry next interval.")
            await asyncio.sleep(settings.event_scan_interval_seconds)

    # --- sync, thread-dispatched unit of work --------------------------------

    def _tick(self) -> EventScanTickOutcome:
        """One full scan: all three sources, three rows, one commit.

        The three scans are each individually failure-contained (see the
        module docstring), so this method has no try/except of its own around
        them — by the time they return, a failure has already become a row.
        """
        detected_at = utcnow_naive()
        rows = [
            self._scan_numeric(detected_at),
            self._scan_gdelt(detected_at),
            self._scan_edgar(detected_at),
        ]

        db: Session = SessionLocal()
        try:
            db.add_all(rows)
            db.commit()
            for row in rows:
                db.refresh(row)
        finally:
            db.close()

        return EventScanTickOutcome(detected_at=detected_at, rows=rows)

    # --- source 1: numeric thresholds ---------------------------------------

    def _scan_numeric(self, detected_at: datetime) -> MacroEventDetection:
        try:
            metrics = self._collect_numeric_metrics()
        except Exception as exc:  # noqa: BLE001 — contained by design; see module docstring
            logger.warning("macro event scan: numeric source failed: %s", exc)
            return self._error_row(detected_at, SOURCE_NUMERIC, exc)

        head = _headline(metrics)
        return MacroEventDetection(
            detected_at=detected_at,
            source=SOURCE_NUMERIC,
            driver=head["key"] if head else None,
            trigger_metric=head["metric"] if head else None,
            trigger_value=head["value"] if head else None,
            trigger_threshold=head["threshold"] if head else None,
            triggered=head is not None,
            escalated=False,
            raw_metrics_json=json.dumps({"metrics": metrics}, default=str),
            error=None,
        )

    def _collect_numeric_metrics(self) -> list[dict]:
        """Every driver and vol index measured this tick, tripped or not.

        A subject that could not be measured (provider returned nothing, or
        fewer than two usable closes) appears with value=None and
        triggered=False, and is NEVER given a fabricated 0.0 move. "Not
        measured" and "measured flat" are different claims and the snapshot
        keeps them different.
        """
        driver_triggers = build_driver_triggers()
        vol_triggers = build_vol_index_triggers()

        price_provider = self._price_provider or YFinanceProvider()
        macro_provider = self._macro_provider or FredProvider()

        etf_symbols = [
            MACRO_DRIVERS_BY_ID[k].symbol
            for k in driver_triggers
            if MACRO_DRIVERS_BY_ID[k].source == DRIVER_SOURCE_ETF
        ]
        symbols = [*etf_symbols, *VOL_INDEX_SYMBOLS.values()]

        # utcnow_naive().date() rather than date.today(): the runner's whole
        # clock is UTC (detected_at above comes from the same source), and a
        # local-time "today" would disagree with it for part of every day.
        end = utcnow_naive().date()
        start = end - timedelta(days=PRICE_LOOKBACK_DAYS)
        prices, _missing = price_provider.get_price_history(symbols, start, end)

        metrics: list[dict] = []

        def closes(symbol: str) -> list[float]:
            """The symbol's own last two usable closes.

            Computed on the symbol's OWN dropna'd series rather than by
            differencing two shared frame rows, because the vol complex
            publishes raggedly — measured live 2026-09-01: ^VIX/^VVIX/^OVX/^GVZ
            had a bar for that date while ^MOVE/^SKEW did not. Differencing
            frame rows would silently compare mismatched dates or yield NaN.
            """
            if prices is None or getattr(prices, "empty", True) or symbol not in prices.columns:
                return []
            series = prices[symbol].dropna()
            return [float(v) for v in series.to_numpy()[-2:]]

        # -- the 13 Layer-1 drivers
        for key, trigger in driver_triggers.items():
            definition = MACRO_DRIVERS_BY_ID[key]
            value: float | None = None

            if definition.source == DRIVER_SOURCE_ETF:
                last_two = closes(definition.symbol)
                if len(last_two) == 2:
                    value = _pct_move(last_two[1], last_two[0])
            else:
                observations = macro_provider.get_latest_observations(
                    definition.symbol, "lin", limit=FRED_OBSERVATION_LIMIT
                )
                # get_latest_observations returns NEWEST FIRST (sort_order=desc).
                if len(observations) >= 2:
                    latest, previous = observations[0].value, observations[1].value
                    if trigger.kind == DRIVER_KIND_PRICE:
                        # DTWEXBGS is an index LEVEL, so its move is a percentage
                        # change — NOT a basis-point difference. See drivers.py.
                        value = _pct_move(latest, previous)
                    else:
                        # FRED reports these in percent; x100 gives basis points,
                        # matching macro_beta.levels_to_moves exactly.
                        value = (latest - previous) * 100.0

            metrics.append(
                {
                    "key": key,
                    "kind": trigger.kind,
                    "symbol": definition.symbol,
                    "label": trigger.label,
                    "metric": (
                        METRIC_DAILY_PCT if trigger.kind == DRIVER_KIND_PRICE else METRIC_DAILY_BPS
                    ),
                    "value": value,
                    "threshold": trigger.threshold,
                    "triggered": value is not None and abs(value) >= trigger.threshold,
                }
            )

        # -- the 6 vol indices
        for key, trigger in vol_triggers.items():
            symbol = VOL_INDEX_SYMBOLS[key]
            last_two = closes(symbol)
            value = _pct_move(last_two[1], last_two[0]) if len(last_two) == 2 else None
            metrics.append(
                {
                    "key": key,
                    "kind": trigger.kind,
                    "symbol": symbol,
                    "label": trigger.label,
                    "metric": METRIC_DAILY_PCT,
                    "value": value,
                    "threshold": trigger.threshold,
                    "triggered": value is not None and abs(value) >= trigger.threshold,
                }
            )

        return metrics

    # --- source 2: GDELT ----------------------------------------------------

    def _scan_gdelt(self, detected_at: datetime) -> MacroEventDetection:
        provider = self._gdelt_provider or GdeltProvider()
        results: list[dict] = []
        errors: list[str] = []

        # WALL-CLOCK BUDGET. See settings.event_gdelt_scan_budget_seconds for
        # the measured failure this prevents: an unbudgeted scan against a
        # degraded GDELT runs up to ~48 minutes against a 300-second tick, and
        # would starve the healthy numeric and EDGAR sources of their own
        # observations. Once the budget is spent, the remaining themes are
        # recorded as NOT MEASURED with an explicit reason — never silently
        # dropped, and never as a measured zero.
        deadline = self._clock() + settings.event_gdelt_scan_budget_seconds

        for theme in GDELT_THEMES:
            # PER-THEME containment, one level finer than per-source: GDELT is
            # flaky enough that one theme failing must not cost the other four
            # their observation this tick.
            for mode, metric, threshold, field in (
                (
                    MODE_TIMELINE_VOLUME,
                    METRIC_GDELT_VOLUME_Z,
                    settings.event_trigger_gdelt_volume_zscore,
                    "zscore",
                ),
                (
                    MODE_TIMELINE_TONE,
                    METRIC_GDELT_TONE_SHIFT,
                    settings.event_trigger_gdelt_tone_shift,
                    "shift",
                ),
            ):
                if self._clock() >= deadline:
                    # Budget spent. Record the remaining checks as NOT MEASURED
                    # with an explicit reason so the observation window can tell
                    # "GDELT was too slow to ask" apart from "asked, nothing
                    # tripped" — two very different facts for a trigger rate.
                    results.append(
                        {
                            "key": theme.key,
                            "mode": mode,
                            "metric": metric,
                            "value": None,
                            "threshold": threshold,
                            "triggered": False,
                            "error": "skipped: per-tick GDELT time budget exhausted",
                        }
                    )
                    continue

                try:
                    signal = provider.fetch_series(theme.key, theme.query, mode)
                except Exception as exc:  # noqa: BLE001 — routine for this service
                    errors.append(f"{theme.key}/{mode}: {exc}")
                    results.append(
                        {
                            "key": theme.key,
                            "mode": mode,
                            "metric": metric,
                            "value": None,
                            "threshold": threshold,
                            "triggered": False,
                            "error": str(exc)[:300],
                        }
                    )
                    continue

                value = getattr(signal, field)
                results.append(
                    {
                        "key": theme.key,
                        "mode": mode,
                        "metric": metric,
                        "value": value,
                        "threshold": threshold,
                        "triggered": value is not None and abs(value) >= threshold,
                        **signal.as_dict(),
                    }
                )

        head = _headline(results)
        # Only a TOTAL failure of every query is reported as the row's error.
        # A partial failure is already recorded per-theme inside the snapshot,
        # and flagging the whole row as errored would wrongly discard the
        # themes that did answer.
        all_failed = bool(results) and all(r.get("error") for r in results)
        return MacroEventDetection(
            detected_at=detected_at,
            source=SOURCE_GDELT,
            driver=head["key"] if head else None,
            trigger_metric=head["metric"] if head else None,
            trigger_value=head["value"] if head else None,
            trigger_threshold=head["threshold"] if head else None,
            triggered=head is not None,
            escalated=False,
            raw_metrics_json=json.dumps({"themes": results}, default=str),
            error="; ".join(errors)[:2000] if all_failed else None,
        )

    # --- source 3: SEC EDGAR ------------------------------------------------

    def _scan_edgar(self, detected_at: datetime) -> MacroEventDetection:
        try:
            universe_ciks = self._resolve_universe_ciks()
        except Exception as exc:  # noqa: BLE001 — contained by design
            logger.warning("macro event scan: EDGAR CIK map failed: %s", exc)
            return self._error_row(detected_at, SOURCE_EDGAR, exc)

        provider = self._edgar_provider or SecEdgarRssProvider()
        results: list[dict] = []
        errors: list[str] = []

        for form_type in EDGAR_WATCHED_FORM_TYPES:
            try:
                entries = provider.fetch_latest_filings(form_type)
            except Exception as exc:  # noqa: BLE001 — contained per form type
                errors.append(f"{form_type}: {exc}")
                results.append(
                    {
                        "key": form_type,
                        "metric": METRIC_EDGAR_FILING_COUNT,
                        "value": None,
                        "threshold": float(EDGAR_MIN_IN_UNIVERSE_FILINGS_TO_TRIGGER),
                        "triggered": False,
                        "error": str(exc)[:300],
                    }
                )
                continue

            in_universe = [e for e in entries if e.cik in universe_ciks]
            results.append(
                {
                    "key": form_type,
                    "metric": METRIC_EDGAR_FILING_COUNT,
                    "value": float(len(in_universe)),
                    "threshold": float(EDGAR_MIN_IN_UNIVERSE_FILINGS_TO_TRIGGER),
                    "triggered": len(in_universe) >= EDGAR_MIN_IN_UNIVERSE_FILINGS_TO_TRIGGER,
                    # The feed total is kept alongside the in-universe count so
                    # the observation window can tell "nothing was filed" from
                    # "plenty was filed, none by a company we track" — two very
                    # different reasons for a non-trigger.
                    "n_feed_entries": len(entries),
                    "filings": [
                        {
                            "cik": e.cik,
                            "company": e.company_name,
                            "form": e.form_type,
                            "role": e.role,
                            "accession": e.accession_number,
                            "items": list(e.item_numbers),
                            "url": e.url,
                            "updated_at": e.updated_at.isoformat() if e.updated_at else None,
                        }
                        for e in in_universe
                    ],
                }
            )

        head = _headline(results)
        all_failed = bool(results) and all(r.get("error") for r in results)
        return MacroEventDetection(
            detected_at=detected_at,
            source=SOURCE_EDGAR,
            driver=head["key"] if head else None,
            trigger_metric=head["metric"] if head else None,
            trigger_value=head["value"] if head else None,
            trigger_threshold=head["threshold"] if head else None,
            triggered=head is not None,
            escalated=False,
            raw_metrics_json=json.dumps({"forms": results}, default=str),
            error="; ".join(errors)[:2000] if all_failed else None,
        )

    def _resolve_universe_ciks(self) -> set[int]:
        """CIKs of the point-in-time universe.

        The Latest Filings feed carries a CIK but NO TICKER (verified live), so
        the mapping goes through SEC's own company_tickers.json, INVERTED —
        reusing EdgarXbrlProvider's existing, disk-cached map rather than
        inventing a second ticker->CIK source that could disagree with it.

        Known and inherited limit, already documented on that provider: the SEC
        file maps CURRENT tickers only, so a delisted or renamed constituent
        resolves no CIK and its filings are invisible to this scan.
        """
        if self._universe_ciks is None:
            # max_cache_age_days is set rather than left at its default None:
            # SEC's company_tickers.json is a MUTABLE document, and this is a
            # long-lived process, so an unbounded disk cache would freeze the
            # ticker->CIK map at whatever was on disk when the scanner first
            # ran. That is the same reasoning EdgarXbrlProvider's own docstring
            # gives for the live forward-validation path.
            provider = self._cik_map_provider or EdgarXbrlProvider(max_cache_age_days=7)
            cik_map = provider.get_ticker_cik_map()
            universe = self._universe if self._universe is not None else SCREENING_UNIVERSE
            wanted = set(universe)
            self._universe_ciks = {cik for t, cik in cik_map.items() if t in wanted}
        return self._universe_ciks

    # --- shared ---------------------------------------------------------------

    @staticmethod
    def _error_row(
        detected_at: datetime, source: str, exc: Exception
    ) -> MacroEventDetection:
        """A source that failed outright still writes its row — with no
        measurement, `triggered=False`, and the reason recorded. Writing
        nothing would make a failure indistinguishable from a quiet tick and
        would bias the observed trigger rate downward."""
        return MacroEventDetection(
            detected_at=detected_at,
            source=source,
            driver=None,
            trigger_metric=None,
            trigger_value=None,
            trigger_threshold=None,
            triggered=False,
            escalated=False,
            raw_metrics_json=json.dumps({"error": str(exc)[:2000]}),
            error=f"{type(exc).__name__}: {exc}"[:2000],
        )
