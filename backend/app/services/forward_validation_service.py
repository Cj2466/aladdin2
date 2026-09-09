import hashlib
import json
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.forward_validation import ForwardValidationRegistration
from app.models.user import User
from app.services.research_lab import metrics
from app.services.research_lab.deflated_sharpe import (
    compute_return_stats,
    probabilistic_sharpe_ratio,
)
from app.services.research_lab.engine import (
    WalkForwardState,
    serialize_walk_forward_state,
)

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

# ADVISORY ONLY SINCE 2026-09-09. Until then a True from check_underperformance
# set the registration's status to "underperforming" — permanently, with no
# automatic reversal, and with the row dropped from every runner's
# ACTIVE_STATUSES so it never accumulated another day. The criteria audit
# (data/research_runs/criteria_audit_2026-09-09/CRITERIA_AUDIT_2026-09-09.md,
# finding F2, Monte Carlo in underperf_mc.py / underperf_mc_fattail.py, and an
# AR(1) check in criteria_fix_2026-09-09/underperf_mc_ar1.py) measured what
# that rule actually does. The standard error of a 60-day annualized Sharpe
# is about sqrt(1/60) * sqrt(252) ~= 2.05, so "trailing Sharpe <= -0.5" sits a
# quarter of a standard error below zero, and evaluating it on every new day
# gives a real edge dozens of chances to trip it by luck:
#
#   true annual Sharpe 1.0 -> flagged within its own 126-day graduation
#                            window with P ~= 0.66, within a year P ~= 0.92
#   true annual Sharpe 0.0 -> P ~= 0.84 / 0.99
#
# A rule that kills a genuine Sharpe-1.0 strategy two times in three, and a
# null one five times in six, is not discriminating between them; it was
# never calibrated to (the comment above says so). It had never fired only
# because no registration had reached 60 realized days. Under paper tracking
# the two error costs are wildly asymmetric — a slot that keeps ticking costs
# nothing, a real edge killed and (via the research runner's known-
# underperforming skip) never re-registered is lost for good — and CLAUDE.md
# rule 6 already says a live registration's operational status is the
# project owner's decision, never an automatic one. So the runners no longer
# change status on this signal. What survives is the SIGNAL, surfaced on the
# API/dashboard next to a calibrated companion (the whole-record PSR below)
# for a human to act on; the "underperforming" status value itself remains
# valid as a state a human may set. Registrations whose stored
# registration_rationale (written before 2026-09-09) still describes the
# permanent rule are describing the rule as it stood when they were written.


@dataclass(frozen=True)
class UnderperformanceAdvisory:
    """What the dashboard shows instead of a status flip.

    `trailing_flag` is check_underperformance's own verdict, unchanged, so
    a reader can see exactly when the old rule WOULD have fired.
    `whole_record_psr_vs_zero` is the calibrated companion: the probability
    that the true Sharpe of the ENTIRE realized record exceeds zero
    (deflated_sharpe.probabilistic_sharpe_ratio against a zero benchmark,
    with the record's own skew/kurtosis). No deflation is applied — a
    forward record is a single pre-registered test, not the best of a grid —
    and it is deliberately not a rule: it is the number a human should be
    looking at when deciding whether a registration has earned retirement.
    Both Sharpe fields are None below MIN_FORWARD_DAYS_FOR_SHARPE realized
    days, for the reason that constant states."""

    n_realized_days: int
    trailing_flag: bool
    trailing_sharpe_annualized: float | None
    whole_record_sharpe_annualized: float | None
    whole_record_psr_vs_zero: float | None


def check_underperformance(
    day_results: list[dict], *, periods_per_year: float = metrics.TRADING_DAYS_PER_YEAR
) -> bool:
    """True iff the trailing UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS days'
    realized net returns have an annualized Sharpe at or below
    UNDERPERFORMANCE_SHARPE_THRESHOLD. False (never flagged) below the
    lookback floor — same "not enough data to judge, so don't" convention
    as MIN_FORWARD_DAYS_FOR_SHARPE above.

    ADVISORY since 2026-09-09 (see the block above): nothing changes a
    registration's status on this value any more. The function and its
    threshold are unchanged so the dashboard can show exactly what the
    retired rule would have said.

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


def underperformance_advisory(
    day_results: list[dict], *, periods_per_year: float = metrics.TRADING_DAYS_PER_YEAR
) -> UnderperformanceAdvisory:
    """The advisory bundle for one registration's realized day results
    (the caller filters to realized days on the cross-sectional path, as
    it already does for check_underperformance)."""
    n = len(day_results)
    trailing_flag = check_underperformance(day_results, periods_per_year=periods_per_year)

    trailing_sharpe = None
    if n >= UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS:
        trailing = pd.Series([d["net_return"] for d in day_results[-UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS:]])
        trailing_sharpe = metrics.sharpe_ratio(trailing, periods_per_year=periods_per_year)

    whole_sharpe = None
    psr = None
    if n >= MIN_FORWARD_DAYS_FOR_SHARPE:
        net_returns = pd.Series([d["net_return"] for d in day_results], dtype=float)
        whole_sharpe = metrics.sharpe_ratio(net_returns, periods_per_year=periods_per_year)
        stats = compute_return_stats(net_returns)
        if stats is not None:
            # Per-period scale on both sides, as probabilistic_sharpe_ratio
            # requires: the annualized whole_sharpe is NOT what goes in.
            sr_per_period = float(net_returns.mean() / net_returns.std(ddof=1))
            if np.isfinite(sr_per_period):
                psr = probabilistic_sharpe_ratio(sr_per_period, 0.0, stats.n, stats.skewness, stats.kurtosis)

    return UnderperformanceAdvisory(
        n_realized_days=n,
        trailing_flag=trailing_flag,
        trailing_sharpe_annualized=trailing_sharpe,
        whole_record_sharpe_annualized=whole_sharpe,
        whole_record_psr_vs_zero=psr,
    )


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
