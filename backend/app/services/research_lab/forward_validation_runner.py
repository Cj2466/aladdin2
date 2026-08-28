import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select

from app import dependencies
from app.config import settings
from app.db import SessionLocal
from app.models.forward_validation import ForwardValidationRegistration
from app.services.forward_validation_service import check_underperformance
from app.services.market_data.base import MarketDataError
from app.services.market_data.price_cache import get_price_history_cached
from app.services.research_lab.engine import (
    MAX_CATCHUP_ROWS_PER_TICK,
    DayResult,
    ForwardStep,
    Trade,
    WalkForwardConfig,
    advance_forward_validation,
    deserialize_walk_forward_state,
    rows_to_process,
    serialize_walk_forward_state,
)
from app.services.research_lab.strategy_registry import get_adapter
from app.services.risk.errors import MissingTickerDataError
from app.time_utils import utcnow_naive

logger = logging.getLogger(__name__)

# Statuses that keep ticking, and the same set the graduation/
# underperformance transitions are evaluated against. "underperforming" is
# deliberately absent and deliberately not auto-reversible: once flagged, a
# registration is parked on purpose, so neither a normal tick nor the
# one-time backfill may ever resume it.
ACTIVE_STATUSES = ("in_progress", "forward_validated")


@dataclass
class _RegistrationSnapshot:
    """Plain data crossing the thread/session boundary, not a detached ORM
    instance — same rationale as AlertChecker's _PriceRuleSnapshot."""

    id: int
    strategy_name: str
    ticker_a: str
    ticker_b: str
    fit_window_days: int
    entry_z: float
    exit_z: float
    cost_bps: float
    last_processed_date: date | None
    min_trading_days_threshold: int
    n_forward_trading_days: int
    carry_state_json: str
    day_results_json: str
    trades_json: str


def _day_result_to_dict(day_result: DayResult) -> dict:
    return {
        "date": day_result.date.strftime("%Y-%m-%d"),
        "position": day_result.position,
        "z_score": day_result.z_score,
        "raw_return": day_result.raw_return,
        "cost": day_result.cost,
        "net_return": day_result.net_return,
        "equity": day_result.equity,
    }


def _trade_to_dict(trade: Trade) -> dict:
    return {
        "entry_date": trade.entry_date.strftime("%Y-%m-%d"),
        "exit_date": trade.exit_date.strftime("%Y-%m-%d") if trade.exit_date is not None else None,
        "direction": trade.direction,
        "holding_days": trade.holding_days,
        "trade_return": trade.trade_return,
        "still_open": trade.still_open,
    }


def apply_forward_steps(registration: ForwardValidationRegistration, steps: list[ForwardStep]) -> int:
    """Fold a chronological list of processed real days into a registration
    row, and return how many were actually applied.

    THE WHOLE POINT OF THIS FUNCTION IS THAT IT IS PER-DAY. Every field it
    writes is advanced exactly once per real trading day, and the two status
    transitions are evaluated after EVERY day rather than once per tick —
    which is what makes a catch-up over N missed days indistinguishable
    from N separate ticks that each caught one day. Concretely:

      * n_forward_trading_days increments once per day, so a day the
        process happened to be asleep for still counts toward
        MIN_FORWARD_VALIDATION_TRADING_DAYS.
      * graduation fires on the day the count actually crosses the
        threshold, not on whichever day a tick happened to land.
      * underperformance is judged on the trailing window AS IT STOOD on
        each day, and a day that flips the registration STOPS the replay
        (the `break`) — because in a never-missed history that registration
        would simply not have been loaded on the following day's tick.
        Continuing past it would accumulate days a real history would
        never have had.

    graduated_at/last_ticked_at are the one thing a replay cannot
    reconstruct: they are wall-clock stamps of when a milestone was
    RECORDED, and the wall clock for a missed day has passed. They are set
    to now, which is honest — the day counts are the load-bearing numbers,
    and those are exact."""
    day_results = json.loads(registration.day_results_json)
    trades = json.loads(registration.trades_json)

    applied = 0
    for step in steps:
        day_results.append(_day_result_to_dict(step.day_result))
        if step.closed_trade is not None:
            trades.append(_trade_to_dict(step.closed_trade))
        applied += 1

        registration.carry_state_json = json.dumps(serialize_walk_forward_state(step.state))
        registration.n_forward_trading_days += 1
        registration.last_processed_date = step.day_result.date.date()

        # Keep ticking after graduation — more real evidence is never
        # harmful, and graduated_at is a one-time milestone marker, not a
        # stop signal.
        if (
            registration.status == "in_progress"
            and registration.n_forward_trading_days >= registration.min_trading_days_threshold
        ):
            registration.status = "forward_validated"
            registration.graduated_at = utcnow_naive()

        # Checked AFTER the graduation transition above, deliberately — a
        # registration that just graduated on this same day can still be
        # immediately flagged underperforming if its trailing window is bad
        # enough. Deliberately NOT auto-reversible: once flagged, status
        # stays "underperforming" forever (this check only ever transitions
        # INTO it, never out), and _load_active_registrations' own status
        # filter naturally stops ticking it on future runs.
        if registration.status in ACTIVE_STATUSES and check_underperformance(day_results):
            registration.status = "underperforming"
            break

    registration.day_results_json = json.dumps(day_results)
    registration.trades_json = json.dumps(trades)
    registration.last_ticked_at = utcnow_naive()
    return applied


def unrecoverable_rows(
    index: pd.DatetimeIndex, last_processed_date: date | None, fit_window_days: int
) -> list[date]:
    """Trading days that are newer than last_processed_date but sit too
    early in the loaded frame to have a full fit window in front of them,
    so they cannot be replayed under the same rules as every other day.

    Returned rather than silently dropped: "a day was lost" is exactly the
    failure this whole change exists to stop happening invisibly, and the
    honest response to a gap older than the loaded price window is to SAY
    SO (and widen the window — which is what the one-time backfill does),
    not to skip it quietly."""
    if last_processed_date is None:
        return []
    return [index[p].date() for p in range(min(fit_window_days, len(index))) if index[p].date() > last_processed_date]


def replay_registration(
    db,
    snapshot: _RegistrationSnapshot,
    raw_data: pd.DataFrame,
    *,
    max_rows: int = MAX_CATCHUP_ROWS_PER_TICK,
    commit: bool = True,
) -> int:
    """Advance one registration onto every unprocessed row of `raw_data` and
    persist the result. Returns the number of real trading days applied (0
    is the common case — no new row — and must be a pure no-op).

    Module-level, and shared verbatim by the live tick and the one-time
    backfill, so a recovered day and a live day are not merely "computed
    the same way" by inspection — they are literally the same code.

    `commit=False` leaves the mutated row pending in `db` for the caller to
    inspect and then roll back: the one-time backfill's dry-run mode, which
    exists because this rewrites real financial tracking state and an
    operator should be able to read the exact before/after first."""
    positions = rows_to_process(raw_data.index, snapshot.last_processed_date, snapshot.fit_window_days, max_rows)
    lost = unrecoverable_rows(raw_data.index, snapshot.last_processed_date, snapshot.fit_window_days)
    if lost:
        logger.error(
            "Forward validation %s: %s trading day(s) between %s and %s are older than the loaded price "
            "window's fit-window floor and CANNOT be replayed from it (%s...%s). Re-run the one-time "
            "backfill, which widens the window, if these days matter.",
            snapshot.id,
            len(lost),
            snapshot.last_processed_date,
            raw_data.index[-1].date(),
            lost[0],
            lost[-1],
        )
    if not positions:
        return 0  # no new trading day yet — the common case on most ticks, and cheap: a same-day
        # repeat is a pure get_price_history_cached hit, no network call.
    if len(positions) > 1:
        logger.info(
            "Forward validation %s: catching up %s missed trading day(s) (%s..%s) that a single-day tick "
            "would have skipped permanently.",
            snapshot.id,
            len(positions),
            raw_data.index[positions[0]].date(),
            raw_data.index[positions[-1]].date(),
        )

    adapter = get_adapter(snapshot.strategy_name)
    config = WalkForwardConfig(
        fit_window_days=snapshot.fit_window_days,
        entry_z=snapshot.entry_z,
        exit_z=snapshot.exit_z,
        cost_bps=snapshot.cost_bps,
    )
    state = deserialize_walk_forward_state(json.loads(snapshot.carry_state_json))
    steps = advance_forward_validation(
        raw_data,
        config,
        adapter.fit_fn,
        adapter.return_fn,
        state,
        snapshot.last_processed_date,
        adapter.decide_position_fn,
        adapter.direction_labels,
        max_rows,
    )

    registration = db.get(ForwardValidationRegistration, snapshot.id)
    if registration is None:
        return 0  # deleted between load and process

    if registration.last_processed_date != snapshot.last_processed_date:
        # OPTIMISTIC CONCURRENCY, and the reason this is a hard refusal
        # rather than a merge: `steps` was computed by chaining forward from
        # the SNAPSHOT's carry state, so if something else has advanced this
        # row since the snapshot was taken, appending them would both
        # double-count days and overwrite the newer carry state with one
        # derived from a stale chain. Doing nothing is always safe — the
        # next pass simply resumes from whatever the row now says. This is
        # what makes the one-time backfill safe to run against a database a
        # live runner is also ticking.
        logger.warning(
            "Forward validation %s advanced concurrently (last_processed_date %s -> %s); "
            "discarding this pass rather than replaying from a stale state.",
            snapshot.id,
            snapshot.last_processed_date,
            registration.last_processed_date,
        )
        return 0

    applied = apply_forward_steps(registration, steps)
    if commit:
        db.commit()
    else:
        db.flush()
    return applied


class ForwardValidationRunner:
    """Periodic background task, launched alongside AlertChecker and
    FinnhubWebSocketClient in main.py's lifespan. Advances every active
    forward-validation registration onto EVERY real trading day the price
    history has published since that registration was last processed, using
    the exact same step_one_day the batch backtest uses — not a second
    implementation that could quietly drift out of sync.

    "Every day since", not "the latest day": a tick that skipped straight to
    the newest row would permanently lose every trading day the process
    happened to miss (a sleeping free-tier host, a transient price-fetch
    failure, a deploy restart). Those days would never be counted toward
    MIN_FORWARD_VALIDATION_TRADING_DAYS, never logged, and never retried —
    silently shortening the one measurement this project's whole
    forward-validation methodology rests on."""

    async def run(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Forward validation tick failed; will retry next interval.")
            await asyncio.sleep(settings.forward_validation_check_interval_seconds)

    async def _tick(self) -> None:
        registrations = await asyncio.to_thread(self._load_active_registrations)
        if not registrations:
            return
        results = await asyncio.gather(
            *(asyncio.to_thread(self._process_registration, r) for r in registrations),
            return_exceptions=True,
        )
        for reg, result in zip(registrations, results, strict=True):
            if isinstance(result, Exception):
                logger.warning("Forward validation tick failed for registration %s: %s", reg.id, result)

    # --- sync, thread-dispatched units of work -------------------------------

    def _load_active_registrations(self) -> list[_RegistrationSnapshot]:
        db = SessionLocal()
        try:
            rows = (
                db.execute(
                    select(ForwardValidationRegistration).where(
                        ForwardValidationRegistration.status.in_(ACTIVE_STATUSES)
                    )
                )
                .scalars()
                .all()
            )
            return [
                _RegistrationSnapshot(
                    id=r.id,
                    strategy_name=r.strategy_name,
                    ticker_a=r.ticker_a,
                    ticker_b=r.ticker_b,
                    fit_window_days=r.fit_window_days,
                    entry_z=r.entry_z,
                    exit_z=r.exit_z,
                    cost_bps=r.cost_bps,
                    last_processed_date=r.last_processed_date,
                    min_trading_days_threshold=r.min_trading_days_threshold,
                    n_forward_trading_days=r.n_forward_trading_days,
                    carry_state_json=r.carry_state_json,
                    day_results_json=r.day_results_json,
                    trades_json=r.trades_json,
                )
                for r in rows
            ]
        finally:
            db.close()

    def _process_registration(self, snapshot: _RegistrationSnapshot) -> None:
        db = SessionLocal()
        try:
            # UTC, not date.today() — get_price_history's `end` is exclusive
            # (yf.download's is), so requesting end=today correctly excludes
            # today's still-forming bar ONLY if "today" is UTC's today. The
            # LOCAL date is wrong whenever local time has run ahead of UTC
            # (here, 00:00-07:00 Bangkok is still the previous UTC day, which
            # is 17:00-00:00 UTC — squarely inside the US session): at that
            # hour date.today() requests one day too many and gets back a bar
            # that is still forming, which this runner would then realize as
            # a permanent daily return and, having advanced
            # last_processed_date past it, never revisit. Same bug class as
            # the fix already documented in the cross-sectional runner and in
            # autonomous_portfolio_runner.
            #
            # The cost, stated rather than discovered later: during those
            # same hours `end` is one day behind price_cache's own
            # LOCAL-date is_rolling_window test, so its 4-day staleness
            # tolerance does not apply and each tick refetches instead of
            # hitting the cache. That is extra network, never wrong data —
            # and the bar it declines to read early is not lost, because the
            # catch-up loop below picks it up on the next tick. Which is the
            # point: deferring a day is now cheap, whereas realizing a
            # half-formed one was permanent.
            end = utcnow_naive().date()
            # Generous buffer for weekends/holidays on top of
            # get_price_history_cached's own rolling-window tolerance. It is
            # also what bounds how long an outage this runner can recover
            # from on its own: only days still inside this window have a full
            # fit window available (see unrecoverable_rows, and the one-time
            # backfill for the older-than-this case).
            start = end - timedelta(days=snapshot.fit_window_days * 2 + 30)
            raw_data = self._build_raw_data(db, snapshot, start, end)
            if raw_data is None:
                return
            replay_registration(db, snapshot, raw_data)
        finally:
            db.close()

    def _build_raw_data(
        self, db, snapshot: _RegistrationSnapshot, start: date, end: date
    ) -> pd.DataFrame | None:
        """Fetch prices and build the strategy's raw_data frame, or None if
        this registration can't be advanced right now. Extracted so the
        one-time backfill builds the frame through the same code path (and
        the same cache) the live tick does, differing only in the window."""
        adapter = get_adapter(snapshot.strategy_name)
        # Deduped: a single-asset strategy's snapshot has ticker_a == ticker_b.
        required_tickers = list(dict.fromkeys([snapshot.ticker_a, snapshot.ticker_b]))

        try:
            prices, _missing = get_price_history_cached(db, dependencies.provider, required_tickers, start, end)
            missing_required = [t for t in required_tickers if t not in prices.columns]
            if missing_required:
                raise MissingTickerDataError(missing_required, label="pair" if len(required_tickers) > 1 else "ticker")
        except (MarketDataError, MissingTickerDataError) as exc:
            logger.warning("Forward validation %s: could not fetch prices this tick: %s", snapshot.id, exc)
            return None

        raw_data = adapter.build_raw_data(prices, snapshot.ticker_a, snapshot.ticker_b)
        if raw_data.empty or len(raw_data) <= snapshot.fit_window_days:
            # Defensive only — a registration is only ever created from
            # an already-"ok" backtest, which by definition already had
            # enough history at that point.
            return None
        return raw_data
