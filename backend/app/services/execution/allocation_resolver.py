import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.experiment_run import ExperimentRun
from app.models.forward_validation import ForwardValidationRegistration
from app.models.strategy_portfolio_allocation import StrategyPortfolioAllocation
from app.services.forward_validation_service import compute_forward_validation_config_hash

logger = logging.getLogger(__name__)

# Only a registration that has cleared its own MIN_FORWARD_VALIDATION_TRADING_DAYS
# evidence bar may be traded. "in_progress" is deliberately excluded: putting
# capital behind a configuration that has not yet survived 126 real
# out-of-sample trading days is a materially different decision from continuing
# to accumulate statistics on it. "underperforming" is excluded for the reason
# that status exists at all. Conservative, and trivial to relax later.
TRADEABLE_REGISTRATION_STATUS = "forward_validated"


def resolve_registration(
    db: Session, allocation: StrategyPortfolioAllocation, user_id: int
) -> ForwardValidationRegistration | None:
    """Map a Phase 4 portfolio allocation to the live signal it should trade.

    An allocation points at an ExperimentRun (a backtest). The thing that
    carries a CURRENT position is the ForwardValidationRegistration tracking
    that same configuration, advanced one real trading day per
    ForwardValidationRunner tick. compute_forward_validation_config_hash hashes
    exactly the seven config fields ExperimentRun stores as typed columns, so
    this join is a mechanical hash lookup, not a fuzzy match — the same
    identity AutonomousPortfolioRunner._config_hash_for_run already relies on.

    Returns None (never raises) when nothing matches: one unregistered or
    not-yet-graduated allocation must never cost the whole tick.
    """
    run = db.get(ExperimentRun, allocation.experiment_run_id)
    if run is None:
        logger.warning(
            "Execution: allocation %s references missing ExperimentRun %s; skipping.",
            allocation.id,
            allocation.experiment_run_id,
        )
        return None

    config_hash = compute_forward_validation_config_hash(
        run.strategy_name,
        run.ticker_a,
        run.ticker_b,
        run.fit_window_days,
        run.entry_z,
        run.exit_z,
        run.cost_bps,
    )
    registration = db.execute(
        select(ForwardValidationRegistration).where(
            ForwardValidationRegistration.user_id == user_id,
            ForwardValidationRegistration.config_hash == config_hash,
            ForwardValidationRegistration.status == TRADEABLE_REGISTRATION_STATUS,
        )
    ).scalar_one_or_none()

    if registration is None:
        logger.warning(
            "Execution: allocation %s (%s %s/%s) has no %r forward-validation registration for "
            "user %s; skipping.",
            allocation.id,
            run.strategy_name,
            run.ticker_a,
            run.ticker_b,
            TRADEABLE_REGISTRATION_STATUS,
            user_id,
        )
    return registration
