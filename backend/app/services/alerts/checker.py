import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update

from app import dependencies
from app.config import settings
from app.db import SessionLocal
from app.models.alert_event import AlertEvent
from app.models.alert_rule import AlertRule
from app.models.portfolio import Portfolio
from app.models.risk_result import RiskResult
from app.models.user import User
from app.services.alerts.email_sender import send_alert_email
from app.services.live_quotes.finnhub_rest import fetch_quote_snapshot
from app.services.market_data.base import MarketDataError
from app.services.market_data.price_cache import get_price_history_cached
from app.services.portfolio_service import compute_risk_input_hash, to_weights_dict
from app.services.risk.engine import compute_portfolio_risk
from app.services.risk.errors import InsufficientHistoryError, MissingTickerDataError
from app.time_utils import utcnow_naive

logger = logging.getLogger(__name__)

RISK_METRIC_STALE_AFTER = timedelta(hours=24)
FIRE_COOLDOWN = timedelta(hours=24)
RISK_RULE_BENCHMARK = "SPY"
RISK_RULE_LOOKBACK_YEARS = 3


@dataclass
class _PriceRuleSnapshot:
    """Plain data, not a detached ORM instance — the rule is loaded in one
    thread-isolated session and evaluated after that session is closed, so
    only plain attributes (never lazy-loaded relationships) may cross the
    boundary."""

    id: int
    ticker: str
    threshold_pct: float
    direction: str
    last_fired_at: datetime | None


class AlertChecker:
    """Periodic background task, launched alongside FinnhubWebSocketClient in
    main.py's lifespan. Every sync DB/yfinance unit of work runs via
    asyncio.to_thread — compute_portfolio_risk's cache-miss path can call
    yf.download, a synchronous multi-second network call that would
    otherwise block the whole event loop (including the live Finnhub WS
    fan-out) for its duration."""

    async def run(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Alert check tick failed; will retry next interval.")
            await asyncio.sleep(settings.alert_check_interval_seconds)

    async def _tick(self) -> None:
        price_rules = await asyncio.to_thread(self._load_active_price_rules)

        distinct_tickers = {r.ticker for r in price_rules}
        snapshots = {}
        if distinct_tickers:
            results = await asyncio.gather(
                *(fetch_quote_snapshot(t) for t in distinct_tickers), return_exceptions=True
            )
            for ticker, result in zip(distinct_tickers, results, strict=True):
                if isinstance(result, Exception):
                    logger.warning("Failed to fetch quote for %s: %s", ticker, result)
                    continue
                snapshots[ticker] = result

        checked_ids: list[int] = []
        for rule in price_rules:
            checked_ids.append(rule.id)
            quote = snapshots.get(rule.ticker)
            if quote is None:
                continue
            if self._crosses(quote.change_percent, rule.threshold_pct, rule.direction) and not (
                self._in_cooldown(rule.last_fired_at)
            ):
                await asyncio.to_thread(self._fire_price_rule, rule.id, quote.change_percent)
        # Always bump last_checked_at regardless of outcome — a persistently
        # broken rule (bad ticker, no quote) must back off, not retry every
        # tick forever.
        if checked_ids:
            await asyncio.to_thread(self._touch_last_checked, checked_ids)

        stale_rule_ids = await asyncio.to_thread(self._load_stale_risk_rule_ids)
        for rule_id in stale_rule_ids:
            await asyncio.to_thread(self._evaluate_risk_rule, rule_id)

    @staticmethod
    def _crosses(observed_percent: float, threshold_pct: float, direction: str) -> bool:
        if direction == "up":
            return observed_percent >= threshold_pct
        return observed_percent <= -threshold_pct

    @staticmethod
    def _in_cooldown(last_fired_at: datetime | None) -> bool:
        if last_fired_at is None:
            return False
        return utcnow_naive() - last_fired_at < FIRE_COOLDOWN

    # --- sync, thread-dispatched units of work -------------------------------

    def _load_active_price_rules(self) -> list[_PriceRuleSnapshot]:
        db = SessionLocal()
        try:
            rows = (
                db.execute(
                    select(AlertRule).where(
                        AlertRule.is_active.is_(True), AlertRule.rule_type == "price_move"
                    )
                )
                .scalars()
                .all()
            )
            return [
                _PriceRuleSnapshot(
                    id=r.id,
                    ticker=r.ticker,
                    threshold_pct=r.threshold_pct,
                    direction=r.direction,
                    last_fired_at=r.last_fired_at,
                )
                for r in rows
            ]
        finally:
            db.close()

    def _touch_last_checked(self, rule_ids: list[int]) -> None:
        db = SessionLocal()
        try:
            db.execute(
                update(AlertRule).where(AlertRule.id.in_(rule_ids)).values(last_checked_at=utcnow_naive())
            )
            db.commit()
        finally:
            db.close()

    def _fire_price_rule(self, rule_id: int, observed_percent: float) -> None:
        db = SessionLocal()
        try:
            rule = db.get(AlertRule, rule_id)
            if rule is None:
                return
            user = db.get(User, rule.user_id)
            message = (
                f"{rule.ticker} moved {observed_percent:+.2f}% today, crossing your "
                f"{rule.direction} {rule.threshold_pct:.1f}% threshold."
            )
            event = AlertEvent(
                alert_rule_id=rule.id,
                user_id=rule.user_id,
                message=message,
                triggered_value=observed_percent,
            )
            db.add(event)
            rule.last_fired_at = utcnow_naive()
            db.flush()
            event.email_sent = send_alert_email(user.email, "Aladdin2 price alert", message) if user else False
            db.commit()
        finally:
            db.close()

    def _load_stale_risk_rule_ids(self) -> list[int]:
        db = SessionLocal()
        try:
            cutoff = utcnow_naive() - RISK_METRIC_STALE_AFTER
            rows = db.execute(
                select(AlertRule.id).where(
                    AlertRule.is_active.is_(True),
                    AlertRule.rule_type == "risk_metric",
                    (AlertRule.last_checked_at.is_(None)) | (AlertRule.last_checked_at < cutoff),
                )
            ).scalars().all()
            return list(rows)
        finally:
            db.close()

    def _evaluate_risk_rule(self, rule_id: int) -> None:
        db = SessionLocal()
        try:
            rule = db.get(AlertRule, rule_id)
            if rule is None or not rule.is_active:
                return
            portfolio = db.get(Portfolio, rule.portfolio_id)
            if portfolio is None:
                rule.last_checked_at = utcnow_naive()
                db.commit()
                return

            weights = to_weights_dict(portfolio)
            if not weights:
                rule.last_checked_at = utcnow_naive()
                db.commit()
                return

            input_hash = compute_risk_input_hash(weights, RISK_RULE_BENCHMARK, RISK_RULE_LOOKBACK_YEARS)
            cached_row = db.execute(
                select(RiskResult).where(
                    RiskResult.portfolio_id == portfolio.id, RiskResult.input_hash == input_hash
                )
            ).scalar_one_or_none()

            if cached_row is not None:
                metrics = json.loads(cached_row.metrics_json)
            else:

                def prices_fn(tickers, start, end):
                    return get_price_history_cached(db, dependencies.provider, tickers, start, end)

                try:
                    result = compute_portfolio_risk(
                        weights, RISK_RULE_BENCHMARK, RISK_RULE_LOOKBACK_YEARS, prices_fn
                    )
                except (MarketDataError, MissingTickerDataError, InsufficientHistoryError):
                    logger.warning("Risk-metric rule %s: could not compute risk this tick.", rule_id)
                    rule.last_checked_at = utcnow_naive()
                    db.commit()
                    return
                metrics = result.model_dump()
                db.add(
                    RiskResult(
                        portfolio_id=portfolio.id,
                        input_hash=input_hash,
                        metrics_json=result.model_dump_json(),
                    )
                )

            rule.last_checked_at = utcnow_naive()

            metric_value = metrics.get(rule.metric)
            if metric_value is None:
                db.commit()
                return

            # threshold_pct is the metric's raw value scaled by 100 — a
            # natural percent reading for volatility/VaR/CVaR (0.032 -> 3.2),
            # and a documented ×100 convention for beta/hhi/avg-correlation,
            # which aren't literally percentages but use the same scaling so
            # every metric shares one comparison rule.
            observed_percent = metric_value * 100
            if self._crosses(observed_percent, rule.threshold_pct, rule.direction) and not (
                self._in_cooldown(rule.last_fired_at)
            ):
                user = db.get(User, rule.user_id)
                message = (
                    f"Portfolio {rule.metric} reached {observed_percent:.2f} "
                    f"({rule.direction} threshold {rule.threshold_pct:.1f})."
                )
                event = AlertEvent(
                    alert_rule_id=rule.id,
                    user_id=rule.user_id,
                    message=message,
                    triggered_value=observed_percent,
                )
                db.add(event)
                rule.last_fired_at = utcnow_naive()
                db.flush()
                event.email_sent = (
                    send_alert_email(user.email, "Aladdin2 risk alert", message) if user else False
                )

            db.commit()
        finally:
            db.close()
