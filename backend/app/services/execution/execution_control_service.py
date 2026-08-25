import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.execution_control import SINGLETON_ID, ExecutionControl
from app.time_utils import utcnow_naive

logger = logging.getLogger(__name__)

# "The same trading day" means the same US-equity session day, not the same
# UTC day and not the same server-local day. A breach at 16:00 ET rolls over
# into the next UTC date four hours later, while the ET session day has not
# changed — using UTC would quietly re-arm trading the same evening, which is
# the unsafe direction. Same zone this repo's market_hours.py already uses.
EASTERN = ZoneInfo("America/New_York")

RESUME_CONFIRMATION = "RESUME LIVE TRADING"
"""The exact string POST /resume requires in its body. Halting has no
confirmation at all — friction belongs only on the direction that can lose
money."""

STARTUP_DEFAULT_REASON = "startup_default"


def get_control(db: Session) -> ExecutionControl:
    """Fetch the singleton, creating it halted if it is somehow absent.

    The migration seeds this row, so the create path is only reachable on a
    database built straight from Base.metadata.create_all (every test, and any
    future dev DB made without alembic). It creates the row HALTED, matching
    the migration's own seed — there is no code path anywhere that brings this
    table into existence in a trading-enabled state.
    """
    control = db.get(ExecutionControl, SINGLETON_ID)
    if control is None:
        control = ExecutionControl(
            id=SINGLETON_ID,
            trading_halted=True,
            halted_reason=STARTUP_DEFAULT_REASON,
            halted_at=utcnow_naive(),
        )
        db.add(control)
        db.commit()
        db.refresh(control)
    return control


def eastern_trading_date(moment: datetime) -> date:
    """The US-equity session date a naive-UTC timestamp belongs to."""
    return moment.replace(tzinfo=ZoneInfo("UTC")).astimezone(EASTERN).date()


def halt(
    db: Session, *, reason: str, user_id: int | None = None, breach_pct: float | None = None
) -> ExecutionControl:
    """Idempotent. Re-halting an already-halted system refreshes the reason but
    never clears a recorded loss breach — the breach timestamp is what blocks
    same-day resume, so a later manual halt must not launder it away."""
    control = get_control(db)
    control.trading_halted = True
    control.halted_reason = reason
    control.halted_at = utcnow_naive()
    control.halted_by_user_id = user_id
    if breach_pct is not None:
        control.daily_loss_breach_at = utcnow_naive()
        control.daily_loss_breach_pct = breach_pct
    db.commit()
    db.refresh(control)
    return control


class ResumeRefused(Exception):
    """Resume was rejected for a stated reason. Carried as an exception rather
    than a bool so the caller cannot forget to check it."""


def resume(db: Session, *, user_id: int, confirmation: str) -> ExecutionControl:
    control = get_control(db)

    if confirmation != RESUME_CONFIRMATION:
        raise ResumeRefused(f"Confirmation must be exactly {RESUME_CONFIRMATION!r}.")

    if control.daily_loss_breach_at is not None:
        breach_day = eastern_trading_date(control.daily_loss_breach_at)
        today = eastern_trading_date(utcnow_naive())
        if breach_day >= today:
            raise ResumeRefused(
                "The daily-loss circuit breaker fired today "
                f"({breach_day.isoformat()}, US market time). Trading cannot be resumed until the "
                "next trading day."
            )

    control.trading_halted = False
    control.halted_reason = None
    control.halted_at = None
    control.halted_by_user_id = None
    control.resumed_at = utcnow_naive()
    control.resumed_by_user_id = user_id
    db.commit()
    db.refresh(control)
    logger.warning("Live trading RESUMED by user %s.", user_id)
    return control


def record_tick(db: Session, status: str) -> None:
    """Observability only — never read by any control-flow decision."""
    control = get_control(db)
    control.last_tick_at = utcnow_naive()
    control.last_tick_status = status[:255]
    db.commit()
