import hashlib
import json
from datetime import date

import pandas as pd
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.forward_validation import ForwardValidationRegistration
from app.models.user import User
from app.services.research_lab import metrics
from app.services.research_lab.engine import WalkForwardState, serialize_walk_forward_state

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

# Reuses ou_pairs.MIN_OUT_OF_SAMPLE_TRADING_DAYS's own floor-below-which-
# data-is-meaningless convention, not an independently derived number.
# Deliberately a TRAILING window, not all-time cumulative — a recent bad
# stretch on an otherwise-good all-time track record must still trigger
# this, not be masked by it.
UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS = 60

# A risk-tolerance judgment call, stated honestly as such — unlike every
# other threshold added this phase, this one is NOT independently
# empirically calibrated against a null distribution; it's a "how much
# real underperformance are we willing to keep funding a daily backtest/
# registration slot for" business decision.
UNDERPERFORMANCE_SHARPE_THRESHOLD = -0.5


def check_underperformance(
    day_results: list[dict], *, periods_per_year: float = metrics.TRADING_DAYS_PER_YEAR
) -> bool:
    """True iff the trailing UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS days'
    realized net returns have an annualized Sharpe at or below
    UNDERPERFORMANCE_SHARPE_THRESHOLD. False (never flagged) below the
    lookback floor — same "not enough data to judge, so don't" convention
    as MIN_FORWARD_DAYS_FOR_SHARPE above.

    periods_per_year is keyword-only and defaulted to TRADING_DAYS_PER_YEAR
    for exactly the reason metrics.sharpe_ratio's own identical parameter
    is: every existing caller — the pairs/momentum forward-validation
    runner, which is the only one that existed before this parameter — is
    byte-for-byte unaffected, and a 24/7/365 family (crypto, see
    metrics.CALENDAR_DAYS_PER_YEAR) passes its own calendar explicitly
    rather than being judged against an exchange year it does not trade on.
    Pinned by a regression test that this function's no-argument behavior is
    unchanged."""
    if len(day_results) < UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS:
        return False
    trailing = day_results[-UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS:]
    net_returns = pd.Series([d["net_return"] for d in trailing])
    return metrics.sharpe_ratio(net_returns, periods_per_year=periods_per_year) <= UNDERPERFORMANCE_SHARPE_THRESHOLD


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


def register_or_get_forward_validation(
    db: Session,
    *,
    user_id: int,
    strategy_name: str,
    ticker_a: str,
    ticker_b: str,
    fit_window_days: int,
    entry_z: float,
    exit_z: float,
    cost_bps: float,
) -> tuple[ForwardValidationRegistration, bool]:
    """Idempotent create-or-return, extracted from the two forward-validation
    POST handlers' duplicated logic — never resets accumulated progress on
    an existing registration. Returns (registration, created)."""
    config_hash = compute_forward_validation_config_hash(
        strategy_name, ticker_a, ticker_b, fit_window_days, entry_z, exit_z, cost_bps
    )
    existing = db.execute(
        select(ForwardValidationRegistration).where(
            ForwardValidationRegistration.user_id == user_id,
            ForwardValidationRegistration.config_hash == config_hash,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    registration = ForwardValidationRegistration(
        user_id=user_id,
        strategy_name=strategy_name,
        ticker_a=ticker_a,
        ticker_b=ticker_b,
        fit_window_days=fit_window_days,
        entry_z=entry_z,
        exit_z=exit_z,
        cost_bps=cost_bps,
        config_hash=config_hash,
        status="in_progress",
        min_trading_days_threshold=MIN_FORWARD_VALIDATION_TRADING_DAYS,
        n_forward_trading_days=0,
        started_at=date.today(),
        carry_state_json=json.dumps(serialize_walk_forward_state(WalkForwardState())),
        day_results_json="[]",
        trades_json="[]",
    )
    db.add(registration)
    db.commit()
    db.refresh(registration)
    return registration, True


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
