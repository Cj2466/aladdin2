import asyncio
import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import SessionLocal
from app.models.experiment_run import ExperimentRun
from app.models.forward_validation import ForwardValidationRegistration
from app.models.strategy_portfolio import StrategyPortfolio
from app.models.strategy_portfolio_allocation import StrategyPortfolioAllocation
from app.services.forward_validation_service import (
    compute_forward_validation_config_hash,
)
from app.services.research_lab.strategy_portfolio_returns import (
    MissingExperimentRunError,
    compute_strategy_portfolio_optimization,
)
from app.services.research_lab.system_account import get_or_create_system_user
from app.services.risk.errors import (
    InsufficientHistoryError,
    OptimizationInfeasibleError,
)
from app.services.risk.optimizer import DEFAULT_MAX_WEIGHT
from app.time_utils import utcnow_naive

logger = logging.getLogger(__name__)

# The name of the single system-owned portfolio this runner maintains.
# Looked up by (system_user_id, name), so the runner is idempotent across
# restarts and never accumulates duplicates.
SYSTEM_PORTFOLIO_NAME = "Autonomous forward-validated portfolio"

# How many graduated strategies must exist before autonomously building and
# optimizing a portfolio at all. Deliberately ABOVE the optimizer's own
# feasibility floor: n * DEFAULT_MAX_WEIGHT >= 1.0 already refuses n < 3 at
# the 0.4 cap, so a gate of 3 would merely restate that error in different
# words. The question this constant answers is a different one — is 1-3
# graduated strategies a portfolio worth auto-building at all?
#
# Measured against the real dev DB (43 stored status="ok" ExperimentRun
# rows, 20 random combinations per size, each a real
# compute_strategy_portfolio_optimization call) — mean number of members
# the optimizer gives a non-zero weight:
#
#     n=3  -> 3.00 of 3     n=6  -> 3.50 of 6     n=20 -> 4.40 of 20
#     n=4  -> 3.00 of 4     n=8  -> 3.55 of 8     n=43 -> 5.00 of 43
#     n=5  -> 3.15 of 5    n=12  -> 4.10 of 12
#
# The 0.4 cap means at most ceil(1/0.4)=3 members can ever carry meaningful
# weight, so at n=3 the optimizer discards NOTHING — every graduated
# strategy gets funded no matter how it looks, and the "optimization" is
# only ordering what you already have, never selecting from it. Real
# selection starts once there is something to reject: ~37% of members are
# zero-weighted at n=5, versus 0% at n=3 and 25% at n=4.
#
# 5 is also the same floor-below-which-don't-trust-it convention this
# codebase already applies at the observation-count level
# (risk/engine.py's MIN_OBS_FOR_ANY_ESTIMATE=20 /
# NOISY_ESTIMATE_TRADING_DAYS=500) and at the trial-count level
# (deflated_sharpe.py's MIN_TRIALS_FOR_DSR=5, "roughly where the estimate
# stops being dominated by which 2-3 trials happened to land in the
# sample") — applied here at the how-many-strategies level. It gives the
# diversification metrics 10 pairwise correlations instead of 3.
MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO = 5


@dataclass
class _GraduatedStrategy:
    """A graduated registration paired with the freshest ExperimentRun that
    matches its exact configuration. Plain data, resolved inside one
    session and carried out of it — same convention as
    ForwardValidationRunner._RegistrationSnapshot."""

    config_hash: str
    registration_id: int
    experiment_run_id: int
    label: str


def _config_hash_for_run(run: ExperimentRun) -> str:
    """compute_forward_validation_config_hash hashes exactly
    (strategy_name, ticker_a, ticker_b, fit_window_days, entry_z, exit_z,
    cost_bps) — the identical 7 fields ExperimentRun stores as typed
    columns. So mapping in either direction between an ExperimentRun and
    the ForwardValidationRegistration tracking that same configuration is a
    mechanical hash lookup, never a fuzzy match. (This is the same identity
    the already-designed Phase 5 allocation resolver relies on, reused here
    rather than re-derived.)"""
    return compute_forward_validation_config_hash(
        run.strategy_name,
        run.ticker_a,
        run.ticker_b,
        run.fit_window_days,
        run.entry_z,
        run.exit_z,
        run.cost_bps,
    )


class AutonomousPortfolioRunner:
    """Periodic background task, launched alongside the other research-lab
    runners in main.py's lifespan. Closes the last manual step in the
    research chain: screening, backtesting, forward-validation registration
    and underperformance pruning all already run with nobody logged in, but
    combining survivors into an actual risk-budgeted portfolio previously
    required a human to click through the UI.

    Each tick does two things against one system-owned StrategyPortfolio:

      1. Membership sync. A ForwardValidationRegistration that reached
         status="forward_validated" (126+ real out-of-sample trading days —
         the project's own MIN_FORWARD_VALIDATION_TRADING_DAYS bar) becomes
         eligible and is added. One that later flips to "underperforming"
         (forward_validation_service.check_underperformance's trailing
         60-day Sharpe rule) is REMOVED — the portfolio-level analogue of
         that rule's "stop funding this": it already stops accumulating new
         evidence for such a registration, and this stops budgeting risk to
         it. Not auto-reversible, for free: G1 only ever transitions INTO
         "underperforming", so a removed strategy can never silently
         reappear.

      2. Re-optimization. Re-runs the same
         compute_strategy_portfolio_optimization the UI's Optimize button
         calls and writes the resulting weights back — a genuine,
         evidence-driven reweighting over time, not a one-time snapshot.

    Every unit of work opens its own SessionLocal, and a failure in one tick
    is logged and retried next interval — the loop itself never dies."""

    async def run(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Autonomous portfolio tick failed; will retry next interval.")
            await asyncio.sleep(settings.autonomous_portfolio_check_interval_seconds)

    async def _tick(self) -> None:
        system_user_id = await asyncio.to_thread(self._ensure_system_user)
        await asyncio.to_thread(self._sync_and_reoptimize, system_user_id)

    # --- sync, thread-dispatched units of work -------------------------------

    def _ensure_system_user(self) -> int:
        db = SessionLocal()
        try:
            return get_or_create_system_user(db).id
        finally:
            db.close()

    def _load_graduated_strategies(self, db: Session, system_user_id: int) -> list[_GraduatedStrategy]:
        """Every system-owned registration that has genuinely graduated,
        resolved to the ExperimentRun carrying its backtested return series.

        Deliberately status == "forward_validated" only: "in_progress" hasn't
        cleared its own out-of-sample evidence bar yet, and "underperforming"
        has been explicitly pruned. Excluding both is what makes membership
        automatic in BOTH directions without any extra bookkeeping."""
        registrations = (
            db.execute(
                select(ForwardValidationRegistration).where(
                    ForwardValidationRegistration.user_id == system_user_id,
                    ForwardValidationRegistration.status == "forward_validated",
                )
            )
            .scalars()
            .all()
        )
        if not registrations:
            return []

        resolved: list[_GraduatedStrategy] = []
        for registration in registrations:
            # ExperimentRun's own input_hash folds in the calendar date, so
            # the same configuration re-run on a later day is a NEW row.
            # Take the most recently computed "ok" one: it carries the
            # freshest price data, which is what makes a re-optimization
            # weeks later a real update rather than a replay of stale numbers.
            run = db.execute(
                select(ExperimentRun)
                .where(
                    ExperimentRun.strategy_name == registration.strategy_name,
                    ExperimentRun.ticker_a == registration.ticker_a,
                    ExperimentRun.ticker_b == registration.ticker_b,
                    ExperimentRun.fit_window_days == registration.fit_window_days,
                    ExperimentRun.entry_z == registration.entry_z,
                    ExperimentRun.exit_z == registration.exit_z,
                    ExperimentRun.cost_bps == registration.cost_bps,
                    ExperimentRun.status == "ok",
                )
                .order_by(ExperimentRun.computed_at.desc(), ExperimentRun.id.desc())
                .limit(1)
            ).scalar_one_or_none()
            if run is None:
                # Graduated, but no usable backtest at that exact config
                # (e.g. every run of it came back "not_mean_reverting").
                # Skip it and keep processing the rest — one unresolvable
                # registration must never cost the whole portfolio a tick.
                logger.info(
                    "Graduated registration %s (%s %s/%s) has no ok ExperimentRun at its config; skipping.",
                    registration.id,
                    registration.strategy_name,
                    registration.ticker_a,
                    registration.ticker_b,
                )
                continue
            resolved.append(
                _GraduatedStrategy(
                    config_hash=registration.config_hash,
                    registration_id=registration.id,
                    experiment_run_id=run.id,
                    label=f"{registration.strategy_name} {registration.ticker_a}/{registration.ticker_b}",
                )
            )
        return resolved

    def _sync_and_reoptimize(self, system_user_id: int) -> None:
        db = SessionLocal()
        try:
            desired = {s.config_hash: s for s in self._load_graduated_strategies(db, system_user_id)}
            portfolio = db.execute(
                select(StrategyPortfolio)
                .where(
                    StrategyPortfolio.user_id == system_user_id,
                    StrategyPortfolio.name == SYSTEM_PORTFOLIO_NAME,
                )
                .options(selectinload(StrategyPortfolio.allocations))
            ).scalar_one_or_none()

            if portfolio is None:
                if len(desired) < MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO:
                    logger.info(
                        "Only %s graduated strategies available (need %s); not building the "
                        "autonomous portfolio yet.",
                        len(desired),
                        MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO,
                    )
                    return
                portfolio = StrategyPortfolio(user_id=system_user_id, name=SYSTEM_PORTFOLIO_NAME)
                db.add(portfolio)
                db.flush()
                logger.info(
                    "Created the autonomous strategy portfolio with %s graduated strategies.",
                    len(desired),
                )

            changed = self._sync_membership(db, portfolio, desired)
            if not portfolio.allocations:
                db.commit()
                return

            today = date.today()
            already_optimized_today = (
                portfolio.last_optimized_at is not None
                and portfolio.last_optimized_at.date() >= today
            )
            # A membership change always forces a reweight regardless of the
            # once-a-day guard: removing an underperformer would otherwise
            # leave the surviving weights summing to less than 1.
            if not changed and already_optimized_today:
                db.commit()
                return

            self._reweight(db, portfolio)
            db.commit()
        finally:
            db.close()

    def _sync_membership(
        self, db: Session, portfolio: StrategyPortfolio, desired: dict[str, _GraduatedStrategy]
    ) -> bool:
        """Add newly-graduated strategies, drop pruned/unresolvable ones,
        and repoint survivors at their freshest ExperimentRun. Returns True
        iff anything actually changed."""
        runs = {}
        run_ids = [a.experiment_run_id for a in portfolio.allocations]
        if run_ids:
            runs = {
                r.id: r
                for r in db.execute(select(ExperimentRun).where(ExperimentRun.id.in_(run_ids)))
                .scalars()
                .all()
            }

        changed = False
        seen: set[str] = set()
        for allocation in list(portfolio.allocations):
            run = runs.get(allocation.experiment_run_id)
            config_hash = _config_hash_for_run(run) if run is not None else None
            target = desired.get(config_hash) if config_hash is not None else None
            if target is None:
                # No longer graduated (pruned as underperforming, deleted,
                # or its run vanished) — stop funding it.
                logger.info(
                    "Removing strategy portfolio allocation %s (run %s): no longer a graduated, "
                    "resolvable registration.",
                    allocation.id,
                    allocation.experiment_run_id,
                )
                portfolio.allocations.remove(allocation)
                changed = True
                continue
            seen.add(config_hash)
            if allocation.experiment_run_id != target.experiment_run_id:
                allocation.experiment_run_id = target.experiment_run_id
                changed = True

        for config_hash, strategy in desired.items():
            if config_hash in seen:
                continue
            logger.info(
                "Adding newly-graduated strategy %s (run %s) to the autonomous portfolio.",
                strategy.label,
                strategy.experiment_run_id,
            )
            portfolio.allocations.append(
                StrategyPortfolioAllocation(
                    experiment_run_id=strategy.experiment_run_id,
                    # Provisional: _reweight overwrites this in the same
                    # transaction. Written anyway so the NOT NULL column is
                    # always satisfiable even if reweighting then fails.
                    weight=1.0 / len(desired),
                )
            )
            changed = True

        return changed

    def _reweight(self, db: Session, portfolio: StrategyPortfolio) -> None:
        """Re-run the same optimizer the UI's Optimize button calls, and
        write the result back. Falls back to equal weight — never to a
        broken portfolio whose weights don't sum to 1 — whenever the
        optimization can't honestly be made."""
        allocations = {a.experiment_run_id: a.weight for a in portfolio.allocations}
        n = len(allocations)
        equal_weight = 1.0 / n

        if n < MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO:
            # Reachable only after pruning drops an existing portfolio below
            # the floor. Hold the survivors equally rather than pretending a
            # too-small optimization is meaningful, and keep waiting for the
            # count to recover.
            logger.info(
                "Autonomous portfolio is down to %s strategies (need %s to optimize); "
                "holding survivors at equal weight.",
                n,
                MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO,
            )
            for allocation in portfolio.allocations:
                allocation.weight = equal_weight
            return

        # The optimizer's "current" comparison is only meaningful against a
        # real allocation; feed it the stored weights, normalized, so a
        # provisional 1/n on a brand-new member can't skew it.
        total = sum(allocations.values())
        current = {k: (v / total if total > 0 else equal_weight) for k, v in allocations.items()}

        try:
            result, measured_years = compute_strategy_portfolio_optimization(
                db, current, settings.risk_free_rate, max_weight=DEFAULT_MAX_WEIGHT
            )
        except (
            MissingExperimentRunError,
            InsufficientHistoryError,
            OptimizationInfeasibleError,
        ) as exc:
            logger.warning(
                "Autonomous portfolio re-optimization failed (%s); holding equal weight.", exc
            )
            for allocation in portfolio.allocations:
                allocation.weight = equal_weight
            return

        optimized = {int(key): weight for key, weight in result.optimized_weights.items()}
        for allocation in portfolio.allocations:
            allocation.weight = optimized.get(allocation.experiment_run_id, equal_weight)
        portfolio.last_optimized_at = utcnow_naive()
        logger.info(
            "Re-optimized the autonomous portfolio over %s strategies and ~%.1f years of "
            "overlapping returns: optimized Sharpe %.2f vs. current %.2f.",
            n,
            measured_years,
            result.optimized.sharpe,
            result.current.sharpe,
        )
