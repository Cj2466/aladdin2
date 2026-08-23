import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select

from app import dependencies
from app.config import settings
from app.db import SessionLocal
from app.models.forward_validation import ForwardValidationRegistration
from app.services.market_data.base import MarketDataError
from app.services.market_data.price_cache import get_price_history_cached
from app.services.research_lab.engine import (
    DayResult,
    Trade,
    WalkForwardConfig,
    deserialize_walk_forward_state,
    serialize_walk_forward_state,
    step_one_day,
)
from app.services.research_lab.strategy_registry import get_adapter
from app.services.risk.errors import MissingTickerDataError
from app.time_utils import utcnow_naive

logger = logging.getLogger(__name__)


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


class ForwardValidationRunner:
    """Periodic background task, launched alongside AlertChecker and
    FinnhubWebSocketClient in main.py's lifespan. Advances every active
    forward-validation registration by at most one real trading day per
    tick, using the exact same step_one_day the batch backtest uses — not
    a second implementation that could quietly drift out of sync."""

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
                        ForwardValidationRegistration.status.in_(["in_progress", "forward_validated"])
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
            adapter = get_adapter(snapshot.strategy_name)
            end = date.today()
            # Generous buffer for weekends/holidays on top of
            # get_price_history_cached's own rolling-window tolerance.
            start = end - timedelta(days=snapshot.fit_window_days * 2 + 30)
            # Deduped: a single-asset strategy's snapshot has ticker_a == ticker_b.
            required_tickers = list(dict.fromkeys([snapshot.ticker_a, snapshot.ticker_b]))

            try:
                prices, _missing = get_price_history_cached(db, dependencies.provider, required_tickers, start, end)
                missing_required = [t for t in required_tickers if t not in prices.columns]
                if missing_required:
                    raise MissingTickerDataError(missing_required, label="pair" if len(required_tickers) > 1 else "ticker")
            except (MarketDataError, MissingTickerDataError) as exc:
                logger.warning("Forward validation %s: could not fetch prices this tick: %s", snapshot.id, exc)
                return

            raw_data = adapter.build_raw_data(prices, snapshot.ticker_a, snapshot.ticker_b)
            if raw_data.empty or len(raw_data) <= snapshot.fit_window_days:
                # Defensive only — a registration is only ever created from
                # an already-"ok" backtest, which by definition already had
                # enough history at that point.
                return

            latest_available_date = raw_data.index[-1].date()
            if snapshot.last_processed_date is not None and latest_available_date <= snapshot.last_processed_date:
                return  # no new trading day yet — the common case on most ticks, and cheap: a same-day
                # repeat is a pure get_price_history_cached hit, no network call.

            window = raw_data.iloc[-(snapshot.fit_window_days + 1) : -1]
            day_row = raw_data.iloc[-1]

            config = WalkForwardConfig(
                fit_window_days=snapshot.fit_window_days,
                entry_z=snapshot.entry_z,
                exit_z=snapshot.exit_z,
                cost_bps=snapshot.cost_bps,
            )
            state = deserialize_walk_forward_state(json.loads(snapshot.carry_state_json))
            new_state, day_result, closed_trade = step_one_day(
                window,
                day_row,
                adapter.fit_fn,
                adapter.return_fn,
                state,
                config,
                adapter.decide_position_fn,
                adapter.direction_labels,
            )

            day_results = json.loads(snapshot.day_results_json)
            day_results.append(_day_result_to_dict(day_result))
            trades = json.loads(snapshot.trades_json)
            if closed_trade is not None:
                trades.append(_trade_to_dict(closed_trade))

            registration = db.get(ForwardValidationRegistration, snapshot.id)
            if registration is None:
                return  # deleted between load and process

            registration.carry_state_json = json.dumps(serialize_walk_forward_state(new_state))
            registration.day_results_json = json.dumps(day_results)
            registration.trades_json = json.dumps(trades)
            registration.n_forward_trading_days = snapshot.n_forward_trading_days + 1
            registration.last_processed_date = latest_available_date
            registration.last_ticked_at = utcnow_naive()

            # Keep ticking after graduation — more real evidence is never
            # harmful, and graduated_at is a one-time milestone marker, not
            # a stop signal.
            if (
                registration.status == "in_progress"
                and registration.n_forward_trading_days >= registration.min_trading_days_threshold
            ):
                registration.status = "forward_validated"
                registration.graduated_at = utcnow_naive()

            db.commit()
        finally:
            db.close()
