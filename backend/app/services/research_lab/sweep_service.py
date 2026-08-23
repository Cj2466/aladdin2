import itertools

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.sweep_job import SweepJob
from app.models.user import User
from app.schemas.sweep import SweepGridSpec

# Large enough for realistic grids (e.g. 5x4x5x2=200), bounded enough that
# a 200-combo sweep completes in single-digit minutes at SweepRunner's
# chosen batch size/interval.
MAX_SWEEP_COMBINATIONS = 200


def expand_sweep_grid(grid: SweepGridSpec) -> list[dict]:
    """Deterministic cartesian product over the 4 parameters, filtering out
    any combo where exit_z >= entry_z — the same invariant
    PairsConfigValidatorMixin already enforces for a single backtest; a
    sweep must never generate a config the single-backtest endpoint would
    itself reject."""
    combos = []
    for fit_window_days, entry_z, exit_z, cost_bps in itertools.product(
        grid.fit_window_days, grid.entry_z, grid.exit_z, grid.cost_bps
    ):
        if exit_z >= entry_z:
            continue
        combos.append(
            {
                "fit_window_days": fit_window_days,
                "entry_z": entry_z,
                "exit_z": exit_z,
                "cost_bps": cost_bps,
            }
        )
    return combos


def get_owned_sweep_job(db: Session, sweep_id: int, user: User) -> SweepJob:
    """404 (not 403) whether missing or owned by someone else — same
    non-enumeration reasoning as get_owned_alert_rule/get_owned_forward_validation_registration."""
    job = db.execute(
        select(SweepJob).where(SweepJob.id == sweep_id, SweepJob.user_id == user.id)
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sweep job not found")
    return job
