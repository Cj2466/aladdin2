import hashlib
import json

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.forward_validation import ForwardValidationRegistration
from app.models.user import User

# ~6 trading months — double MIN_OUT_OF_SAMPLE_TRADING_DAYS (the backtest's
# own statistical floor), half DEFAULT_FIT_WINDOW_DAYS. Long enough to
# plausibly span several FOMC cycles and more than one short-term
# volatility regime, and — unlike a backtest window — can't be gamed by
# picking a favorable historical period, since it's gated by real calendar
# time. Explicitly a floor, not a guarantee of spanning multiple regimes —
# every place this is surfaced (API, UI) must say so.
MIN_FORWARD_VALIDATION_TRADING_DAYS = 126

# A Sharpe computed off a handful of daily returns misrepresents precision
# the data can't support — the same "never look more certain than the data
# supports" principle already applied throughout this app.
MIN_FORWARD_DAYS_FOR_SHARPE = 20


def compute_forward_validation_config_hash(
    strategy_name: str, ticker_a: str, ticker_b: str, fit_window_days: int, entry_z: float, exit_z: float, cost_bps: float
) -> str:
    """Deliberately NOT date-folded (unlike ExperimentRun's cache hash) —
    this is a persistent identity for an ongoing registration, not a daily
    cache key. Deliberately excludes user_id — uniqueness is enforced via
    the (user_id, config_hash) composite constraint, so two users tracking
    the same configuration get two independent rows with the same hash."""
    payload = {
        "strategy_name": strategy_name,
        "ticker_a": ticker_a,
        "ticker_b": ticker_b,
        "fit_window_days": fit_window_days,
        "entry_z": entry_z,
        "exit_z": exit_z,
        "cost_bps": cost_bps,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def get_owned_forward_validation_registration(
    db: Session, registration_id: int, user: User
) -> ForwardValidationRegistration:
    """404 (not 403) whether missing or owned by someone else — same
    non-enumeration reasoning as get_owned_alert_rule/get_owned_portfolio."""
    registration = db.execute(
        select(ForwardValidationRegistration).where(
            ForwardValidationRegistration.id == registration_id,
            ForwardValidationRegistration.user_id == user.id,
        )
    ).scalar_one_or_none()
    if registration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forward validation registration not found")
    return registration
