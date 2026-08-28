"""ONE-TIME RECOVERY of forward-validation trading days that were lost
before the runner learned to catch up.

WHAT WAS LOST, AND WHY IT IS RECOVERABLE. Until this change,
ForwardValidationRunner._process_registration read only `raw_data.iloc[-1]`
— the single newest row — and then set last_processed_date to that row's
date. Any real trading day between the previous last_processed_date and
that newest row was jumped straight over: never counted toward
n_forward_trading_days, never appended to day_results_json, never logged,
never retried. On a free-tier host that sleeps, a transient price-fetch
failure, or a deploy restart, that is a permanent silent shortening of the
MIN_FORWARD_VALIDATION_TRADING_DAYS clock this project's entire
forward-validation methodology is built on.

It is recoverable because nothing about those days was ever destroyed. The
prices still exist, the walk-forward step is a pure function of (fit
window, day row, carry state, config), and carry_state_json holds exactly
the state as of last_processed_date. Replaying the missed rows in
chronological order from that state therefore reconstructs precisely the
history a never-missed-a-tick process would have written — which this
module's tests assert by construction, comparing a gap-recovered
registration byte-for-byte against a day-by-day one.

WHY A SCRIPT RATHER THAN A STARTUP HOOK. Once the runner itself catches up
within a tick, every gap that still fits inside the tick's normal price
window is repaired automatically on the next tick, with no operator action
— which is most realistic outages (roughly six months of trading days for a
252-day fit window). A startup hook would therefore be redundant in the
common case, and actively undesirable in the uncommon one: it would rewrite
real financial tracking state on every process restart, invisibly, many
times a day on a free-tier host that sleeps. Rewriting a live track record
should be a deliberate, reviewed, once-run operation that prints its own
before/after. So: an explicit entry point, with a dry-run mode.

WHAT IT ADDS OVER THE FIXED TICK. Two things. It runs NOW, deterministically
and reportably, without waiting for (or running) the whole app; and it
widens the price window to start from each registration's own
last_processed_date rather than from today, so a gap older than the tick's
rolling window — the only kind the fixed tick genuinely cannot repair — is
recovered too.

  ./venv/bin/python -m app.services.research_lab.forward_validation_backfill --dry-run
  ./venv/bin/python -m app.services.research_lab.forward_validation_backfill --apply

ONE HONEST CAVEAT, which no replay can avoid: prices are fetched ADJUSTED
(yfinance auto_adjust), and adjusted history is not a fixed quantity. A
dividend or split after a missed day restates that day's adjusted return,
and — measured here, not assumed — Yahoo's adjusted closes are only
float32-precise and are re-derived per request, so the same bar fetched
over a different date range differs by up to ~2e-6 relative (246 of 738
overlapping AAPL/MSFT values differed on a same-minute refetch with a
6-day-later `start`). On this project's real registrations that moved the
recorded z_score in the 7th significant digit and left every DECISION —
position, cost, raw/net return, equity — bit-identical, because the
z-scores involved sit far from the entry threshold. It is a real limit
nonetheless: a recovered day is the correct day computed from the best data
that exists now, not a time machine.
"""

import argparse
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from app.db import SessionLocal
from app.models.forward_validation import ForwardValidationRegistration
from app.services.research_lab.engine import rows_to_process
from app.services.research_lab.forward_validation_runner import (
    ForwardValidationRunner,
    _RegistrationSnapshot,
    replay_registration,
    unrecoverable_rows,
)
from app.time_utils import utcnow_naive

logger = logging.getLogger(__name__)


@dataclass
class BackfillOutcome:
    """One registration's before/after, whether or not anything changed —
    "this one had no gap" is a result worth printing, not worth hiding."""

    registration_id: int
    strategy_name: str
    ticker_a: str
    ticker_b: str
    status_before: str
    status_after: str
    last_processed_date_before: date | None
    last_processed_date_after: date | None
    n_forward_trading_days_before: int
    n_forward_trading_days_after: int
    recovered_dates: list[date]
    unrecoverable_dates: list[date]
    note: str

    @property
    def days_recovered(self) -> int:
        return self.n_forward_trading_days_after - self.n_forward_trading_days_before


def backfill_registration(
    db, snapshot: _RegistrationSnapshot, *, today: date, apply: bool = False
) -> BackfillOutcome:
    """Replay every recoverable missed day for one registration.

    The price window deliberately starts from the registration's OWN
    last_processed_date, not from today: the OLDEST missed day is the one
    that needs history in front of it, and anchoring on today would leave
    exactly the days a long outage lost sitting below the fit-window floor
    — the one case the fixed tick cannot repair by itself."""
    runner = ForwardValidationRunner()
    outcome = BackfillOutcome(
        registration_id=snapshot.id,
        strategy_name=snapshot.strategy_name,
        ticker_a=snapshot.ticker_a,
        ticker_b=snapshot.ticker_b,
        status_before="",
        status_after="",
        last_processed_date_before=snapshot.last_processed_date,
        last_processed_date_after=snapshot.last_processed_date,
        n_forward_trading_days_before=snapshot.n_forward_trading_days,
        n_forward_trading_days_after=snapshot.n_forward_trading_days,
        recovered_dates=[],
        unrecoverable_dates=[],
        note="",
    )
    registration = db.get(ForwardValidationRegistration, snapshot.id)
    if registration is None:
        outcome.note = "deleted before backfill ran"
        return outcome
    outcome.status_before = outcome.status_after = registration.status

    if snapshot.last_processed_date is None:
        # NOT a gap, and must not be treated as one. A registration that has
        # never ticked has lost nothing: its first tick is defined to start
        # from the newest row and accumulate forward (see
        # engine.rows_to_process). Replaying history into it here would
        # manufacture a "forward" record out of the backward data the
        # registration was decided on.
        outcome.note = "never ticked — nothing lost, first tick will start from today"
        return outcome

    if snapshot.last_processed_date >= today:
        outcome.note = "already current"
        return outcome

    # Anchor on last_processed_date so the oldest missed day has a full fit
    # window in front of it; same buffer arithmetic the live tick uses.
    start = snapshot.last_processed_date - timedelta(days=snapshot.fit_window_days * 2 + 30)
    raw_data = runner._build_raw_data(db, snapshot, start, today)
    if raw_data is None:
        outcome.note = "price history unavailable — not backfilled"
        return outcome

    outcome.unrecoverable_dates = unrecoverable_rows(
        raw_data.index, snapshot.last_processed_date, snapshot.fit_window_days
    )
    # No cap: this is the deliberate one-time catch-up, and the window above
    # already bounds how many rows can exist.
    positions = rows_to_process(
        raw_data.index, snapshot.last_processed_date, snapshot.fit_window_days, len(raw_data)
    )
    applied = replay_registration(db, snapshot, raw_data, max_rows=len(raw_data), commit=apply)

    outcome.status_after = registration.status
    outcome.last_processed_date_after = registration.last_processed_date
    outcome.n_forward_trading_days_after = registration.n_forward_trading_days
    # `applied` can be shorter than `positions` when a replayed day flipped
    # the registration to "underperforming" and stopped it — the days after
    # that point are correctly NOT recovered, because a live history would
    # never have processed them either.
    outcome.recovered_dates = [raw_data.index[p].date() for p in positions[:applied]]
    if not apply:
        db.rollback()
    if applied == 0:
        outcome.note = "no gap — already at the newest available trading day"
    elif outcome.status_after == "underperforming" and outcome.status_before != "underperforming":
        outcome.note = (
            f"recovered {applied} day(s), then flagged underperforming on "
            f"{outcome.last_processed_date_after} — replay stopped there, exactly as a live tick would have"
        )
    else:
        outcome.note = f"recovered {applied} lost trading day(s)"
    return outcome


def backfill_missed_days(*, today: date | None = None, apply: bool = False) -> list[BackfillOutcome]:
    """Every active registration, in id order.

    Rows are loaded through the LIVE RUNNER'S OWN loader, deliberately: the
    backfill must never be able to operate on a different row set than the
    tick does. That also means the statuses it touches are exactly
    ACTIVE_STATUSES — a registration parked as "underperforming" was parked
    on purpose and stopped ticking on purpose, so it has no lost days to
    recover and is left alone."""
    today = today if today is not None else utcnow_naive().date()
    snapshots = ForwardValidationRunner()._load_active_registrations()

    outcomes: list[BackfillOutcome] = []
    for snapshot in sorted(snapshots, key=lambda s: s.id):
        db = SessionLocal()
        try:
            outcomes.append(backfill_registration(db, snapshot, today=today, apply=apply))
        except Exception:
            logger.exception("Forward validation backfill failed for registration %s.", snapshot.id)
            db.rollback()
        finally:
            db.close()
    return outcomes


def format_report(outcomes: list[BackfillOutcome], *, apply: bool) -> str:
    header = "APPLIED" if apply else "DRY RUN (nothing written)"
    lines = [f"Forward-validation backfill — {header}", ""]
    for o in outcomes:
        lines.append(
            f"  #{o.registration_id:<3} {o.strategy_name:<12} {o.ticker_a}/{o.ticker_b:<8} "
            f"n_forward_trading_days {o.n_forward_trading_days_before} -> {o.n_forward_trading_days_after} "
            f"(+{o.days_recovered})  last_processed {o.last_processed_date_before} -> "
            f"{o.last_processed_date_after}  status {o.status_before} -> {o.status_after}"
        )
        lines.append(f"        {o.note}")
        if o.recovered_dates:
            lines.append(f"        recovered: {', '.join(str(d) for d in o.recovered_dates)}")
        if o.unrecoverable_dates:
            lines.append(
                f"        UNRECOVERABLE (older than the fit-window floor): {len(o.unrecoverable_dates)} day(s), "
                f"{o.unrecoverable_dates[0]}..{o.unrecoverable_dates[-1]}"
            )
    total = sum(o.days_recovered for o in outcomes)
    lines += ["", f"  {len(outcomes)} registration(s); {total} trading day(s) recovered in total."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")
    group.add_argument("--apply", action="store_true", help="write the recovered days to the database")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    outcomes = backfill_missed_days(apply=args.apply)
    # print, not logger: this IS the operator-facing output of the script.
    print(format_report(outcomes, apply=args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
