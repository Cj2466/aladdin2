"""The cross-sectional sibling of ForwardValidationRunner.

Mirrors that class's shape deliberately and closely: the same run/sleep
loop on the same settings.forward_validation_check_interval_seconds, the
same load-snapshots-then-process-in-threads structure, the same plain
_RegistrationSnapshot dataclass crossing the thread/session boundary rather
than a detached ORM instance, the same "deleted between load and process"
re-get before writing, the same keep-ticking-after-graduation and
flag-underperforming-after semantics.

It is a SEPARATE runner rather than an extension of that one because it
reads a separate table (see the model's class docstring for why the table is
separate). That separation is what makes the live pairs/momentum path
provably untouched: ForwardValidationRunner's query, its snapshot shape and
its processing are all exactly as they were, and no row this runner handles
can ever reach it.

ONE PANEL PER FAMILY PER TICK. A cross-sectional family's live panel is a
multi-year, multi-ticker download (the Crypto family's is ~73 coins since
2017), and every registration of that family needs the identical one. This
runner therefore builds each family's panel at most once per tick and shares
it across that family's registrations — the reason _tick groups by
family_key and processes families rather than rows.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models.cross_sectional_forward_validation import (
    CrossSectionalForwardValidationRegistration,
)
from app.services.cross_sectional_forward_validation_service import (
    detect_config_drift,
    detect_spec_drift,
)
from app.services.forward_validation_service import check_underperformance
from app.services.market_data.base import MarketDataError
from app.services.research_lab.cross_sectional_forward import (
    advance_forward_validation,
    day_result_to_dict,
    deserialize_cross_sectional_forward_state,
    formation_to_dict,
    serialize_cross_sectional_forward_state,
)
from app.services.research_lab.cross_sectional_forward_registry import (
    CrossSectionalPanelUnavailableError,
    UnknownCrossSectionalFamilyError,
    UnknownCrossSectionalSpecError,
    config_fingerprint,
    config_identity,
    get_family_adapter,
    resolve_spec,
)
from app.time_utils import utcnow_naive

logger = logging.getLogger(__name__)

# Statuses that keep ticking. "spec_drift" is deliberately absent: a drifted
# registration is parked, not retried, because every further day it
# accumulated would deepen a track record that is a blend of two different
# strategies. Un-parking it is a human decision (delete and re-register),
# exactly as "underperforming" is deliberately not auto-reversible.
#
# "retired" is absent for a different reason and is the whole mechanism by
# which a withdrawn registration stops: the row is intact and its history is
# intact, but the hypothesis was found not to be worth further calendar time,
# so this query must never pick it up again. See
# cross_sectional_forward_validation_service.RETIRED_STATUS.
ACTIVE_STATUSES = ("in_progress", "forward_validated")


@dataclass
class _RegistrationSnapshot:
    """Plain data crossing the thread/session boundary, not a detached ORM
    instance — same rationale as ForwardValidationRunner's own snapshot and
    AlertChecker's _PriceRuleSnapshot."""

    id: int
    family_key: str
    pattern_id: str
    status: str
    started_at: date
    last_processed_date: date | None
    min_trading_days_threshold: int
    n_forward_trading_days: int
    n_formations: int
    spec_fingerprint: str
    config_fingerprint: str
    spec_snapshot_json: str
    config_snapshot_json: str
    carry_state_json: str
    day_results_json: str
    formations_json: str


class CrossSectionalForwardValidationRunner:
    """Periodic background task, launched alongside ForwardValidationRunner
    in main.py's lifespan. Advances every active cross-sectional
    forward-validation registration onto every real trading day the family's
    live panel has published since that registration was last processed,
    using the exact same form_portfolio / realize_formation_day the batch
    cross-sectional backtest uses — not a second implementation that could
    quietly drift out of sync."""

    async def run(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Cross-sectional forward validation tick failed; will retry next interval.")
            await asyncio.sleep(settings.forward_validation_check_interval_seconds)

    async def _tick(self) -> None:
        registrations = await asyncio.to_thread(self._load_active_registrations)
        if not registrations:
            return

        by_family: dict[str, list[_RegistrationSnapshot]] = {}
        for snapshot in registrations:
            by_family.setdefault(snapshot.family_key, []).append(snapshot)

        results = await asyncio.gather(
            *(
                asyncio.to_thread(self._process_family, family_key, snapshots)
                for family_key, snapshots in by_family.items()
            ),
            return_exceptions=True,
        )
        for family_key, result in zip(by_family, results, strict=True):
            if isinstance(result, Exception):
                logger.warning("Cross-sectional forward validation tick failed for family %s: %s", family_key, result)

    # --- sync, thread-dispatched units of work -------------------------------

    def _load_active_registrations(self) -> list[_RegistrationSnapshot]:
        db = SessionLocal()
        try:
            rows = (
                db.execute(
                    select(CrossSectionalForwardValidationRegistration).where(
                        CrossSectionalForwardValidationRegistration.status.in_(ACTIVE_STATUSES)
                    )
                )
                .scalars()
                .all()
            )
            return [
                _RegistrationSnapshot(
                    id=r.id,
                    family_key=r.family_key,
                    pattern_id=r.pattern_id,
                    status=r.status,
                    started_at=r.started_at,
                    last_processed_date=r.last_processed_date,
                    min_trading_days_threshold=r.min_trading_days_threshold,
                    n_forward_trading_days=r.n_forward_trading_days,
                    n_formations=r.n_formations,
                    spec_fingerprint=r.spec_fingerprint,
                    config_fingerprint=r.config_fingerprint,
                    spec_snapshot_json=r.spec_snapshot_json,
                    config_snapshot_json=r.config_snapshot_json,
                    carry_state_json=r.carry_state_json,
                    day_results_json=r.day_results_json,
                    formations_json=r.formations_json,
                )
                for r in rows
            ]
        finally:
            db.close()

    def _process_family(self, family_key: str, snapshots: list[_RegistrationSnapshot]) -> None:
        """Build this family's live panel ONCE, then step every one of its
        registrations onto it.

        The cheap pre-check first: a registration whose last_processed_date
        is already today can have nothing new, whatever the panel says —
        today's row is the newest row that can exist. When that is true of
        every registration of the family, the expensive panel download is
        skipped entirely, which is the common case on most of the day's
        ticks (the pairs runner gets the same effect for free from
        get_price_history_cached; a cross-sectional family fetches outside
        that cache, so it has to be explicit)."""
        # UTC, not date.today() -- yf.download's `end` is exclusive, so
        # requesting end=today correctly excludes today's still-forming bar
        # ONLY if "today" is UTC's today. Using the local date is wrong
        # whenever local time has run ahead of UTC (here, 00:00-07:00
        # Bangkok local is still the PREVIOUS UTC day) -- confirmed live:
        # at that local hour, date.today() would request one day too many
        # and get back a bar that is still forming, which this runner would
        # then realize as a permanent daily return and never revisit. Same
        # bug class as autonomous_portfolio_runner's date.today() fix
        # earlier this session -- see that commit for the general pattern.
        today = utcnow_naive().date()
        pending = [s for s in snapshots if s.last_processed_date is None or s.last_processed_date < today]
        if not pending:
            return

        try:
            adapter = get_family_adapter(family_key)
        except UnknownCrossSectionalFamilyError as exc:
            logger.error("Cross-sectional forward validation: %s", exc)
            return

        try:
            panel = adapter.build_live_panel(today)
        except (CrossSectionalPanelUnavailableError, MarketDataError) as exc:
            logger.warning(
                "Cross-sectional forward validation: could not build family %s's live panel this tick: %s",
                family_key,
                exc,
            )
            return

        config = adapter.build_config()
        cfg_hash_now = config_fingerprint(config)
        cfg_now = config_identity(config)

        for snapshot in pending:
            try:
                self._process_registration(snapshot, adapter, panel, config, cfg_hash_now, cfg_now)
            except Exception:
                logger.exception(
                    "Cross-sectional forward validation tick failed for registration %s (%s/%s).",
                    snapshot.id,
                    snapshot.family_key,
                    snapshot.pattern_id,
                )

    def _process_registration(
        self,
        snapshot: _RegistrationSnapshot,
        adapter,
        panel,
        config,
        cfg_hash_now: str,
        cfg_now: dict,
    ) -> None:
        db = SessionLocal()
        try:
            try:
                _adapter, spec = resolve_spec(snapshot.family_key, snapshot.pattern_id)
            except (UnknownCrossSectionalFamilyError, UnknownCrossSectionalSpecError) as exc:
                self._park_as_drifted(db, snapshot.id, str(exc))
                return

            # DRIFT GATE, before any day is processed. A registration whose
            # family has been edited since it was created must stop, not
            # silently start accumulating a different strategy's returns
            # into the same track record.
            # The snapshot carries every field the drift checks read, so it
            # is passed directly rather than re-reading the ORM row — which
            # would defeat the point of snapshotting across the session
            # boundary in the first place.
            drift = detect_spec_drift(snapshot, adapter, spec) or detect_config_drift(
                snapshot, cfg_hash_now, cfg_now
            )
            if drift is not None:
                self._park_as_drifted(db, snapshot.id, drift)
                return

            state = deserialize_cross_sectional_forward_state(json.loads(snapshot.carry_state_json))
            new_state, day_results = advance_forward_validation(
                panel.data,
                spec,
                config,
                panel.membership_fn,
                state,
                snapshot.last_processed_date,
            )
            if not day_results:
                return  # no new row yet — the common case, and a pure no-op

            stored_days = json.loads(snapshot.day_results_json)
            stored_formations = json.loads(snapshot.formations_json)
            n_realized_new = 0
            for day_result in day_results:
                stored_days.append(day_result_to_dict(day_result))
                if day_result.reformed:
                    stored_formations.append(formation_to_dict(day_result))
                if day_result.realized:
                    n_realized_new += 1

            registration = db.get(CrossSectionalForwardValidationRegistration, snapshot.id)
            if registration is None:
                return  # deleted between load and process

            registration.carry_state_json = json.dumps(serialize_cross_sectional_forward_state(new_state))
            registration.day_results_json = json.dumps(stored_days)
            registration.formations_json = json.dumps(stored_formations)
            registration.n_forward_trading_days = snapshot.n_forward_trading_days + n_realized_new
            registration.n_formations = new_state.n_formations
            registration.last_processed_date = day_results[-1].date.date()
            registration.last_ticked_at = utcnow_naive()

            # Keep ticking after graduation — more real evidence is never
            # harmful, and graduated_at is a one-time milestone marker, not
            # a stop signal. Identical to the pairs path.
            if (
                registration.status == "in_progress"
                and registration.n_forward_trading_days >= registration.min_trading_days_threshold
            ):
                registration.status = "forward_validated"
                registration.graduated_at = utcnow_naive()

            # Checked AFTER the graduation transition, deliberately, and
            # against the FAMILY'S OWN calendar (crypto's year is 365
            # observations, not 252 — see metrics.CALENDAR_DAYS_PER_YEAR).
            # Only REALIZED days are eligible: a formation day with nothing
            # realized against it has no net return to judge.
            #
            # Deliberately NOT auto-reversible, exactly as on the pairs
            # path: once flagged, status stays "underperforming", and
            # ACTIVE_STATUSES naturally stops ticking it on future runs.
            realized_days = [d for d in stored_days if d.get("realized")]
            if registration.status in ACTIVE_STATUSES and check_underperformance(
                realized_days, periods_per_year=config.periods_per_year
            ):
                registration.status = "underperforming"

            db.commit()
        finally:
            db.close()

    def _park_as_drifted(self, db, registration_id: int, reason: str) -> None:
        logger.error(
            "Cross-sectional forward validation %s PARKED as spec_drift and will not tick again: %s",
            registration_id,
            reason,
        )
        registration = db.get(CrossSectionalForwardValidationRegistration, registration_id)
        if registration is None:
            return
        registration.status = "spec_drift"
        registration.last_ticked_at = utcnow_naive()
        db.commit()
