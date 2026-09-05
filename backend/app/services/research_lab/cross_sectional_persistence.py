import json
import logging
from dataclasses import asdict
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cross_sectional_trial_result import CrossSectionalTrialResult

logger = logging.getLogger(__name__)

# The generic writer for EVERY cross-sectional/timing family's per-spec
# screening output, closing a gap found and fixed 2026-08-27: every family
# built so far (Commodities, Buyback, Bonds, FX, IVOL, D1, D2, Round C,
# Crypto, Vol-Regime, Index-removal, Small/mid-cap, Correlation Risk
# Premium) computed real results with nowhere durable to persist them —
# every number only ever existed as ad-hoc script output in a temp
# scratchpad, which directly caused two real incidents the same day this
# was built: a local DB wipe silently destroyed 249 real rows, and a
# synthetic RNG test fixture got mistaken for real archived results by a
# later analysis, producing a fabricated "finding" that only fell apart
# under adversarial re-verification.
#
# Deliberately generic rather than one function per family: every family's
# per-spec result dataclass, however different its own fields are, carries
# the same four things this table actually needs to be useful for future
# analysis (empirical-Bayes shrinkage, effective-N clustering, or just "did
# this number get computed before") — a trial identifier (spec_id in the
# newer timing-style modules, pattern_id in the cross_sectional.py-based
# ones), sharpe_annualized, n_trading_days, and a deflated_sharpe object.
# Extracted via getattr rather than a shared base class, since retrofitting
# ~12 existing, independently-tested result dataclasses onto one base class
# is a much bigger, riskier change than this gap justifies — the two field
# names in practice are a closed set, checked explicitly below rather than
# silently returning None for a typo'd or genuinely new third name.
#
# NOT wired into any of the run_*_screening entrypoints as a default side
# effect: none of those functions currently has a `db: Session` parameter,
# none of them is called from a live/automated runner today (every family
# so far has only ever been invoked from an ad-hoc script), and threading a
# database dependency into ~12 independently-tested, working functions is a
# larger, separate change than closing "there is nowhere to persist to."
# The pattern going forward: run_x_screening(...) to get a summary, then
# persist_cross_sectional_trial_results(db, "x", summary.results, run_tag=...)
# — two calls, not a hidden side effect inside the first one.


def persist_cross_sectional_trial_results(
    db: Session,
    family_key: str,
    results: Sequence[Any],
    run_tag: str,
) -> int:
    """Writes one CrossSectionalTrialResult row per element of `results`.
    Commits and returns the row count.

    `run_tag` is mandatory and free-text on purpose — there is no default,
    so every call site has to consciously choose a label rather than
    accepting a generic one that would make a real production run
    indistinguishable from a one-off dev/test invocation at read time. Use
    something that says what this run actually was, e.g.
    "production_2026-08-27" or "adhoc_recheck_after_d1_fix" — not "run" or
    "test".

    Raises ValueError on the first result missing a required field, rather
    than silently skipping it — a family module with a genuinely new
    result shape needs this function taught about it explicitly, not a
    partial, silently-incomplete write that looks complete."""
    if not run_tag or not run_tag.strip():
        raise ValueError("run_tag is mandatory and must be non-empty — see module docstring")
    if not results:
        raise ValueError(
            f"persist_cross_sectional_trial_results called with zero results for "
            f"family_key={family_key!r} — if this family genuinely produced no "
            "replayable specs this run, that is itself worth a row or a log line "
            "at the call site, not a silent no-op here."
        )

    rows = []
    for r in results:
        trial_id = getattr(r, "spec_id", None)
        if trial_id is None:
            trial_id = getattr(r, "pattern_id", None)
        if trial_id is None:
            raise ValueError(
                f"result {r!r} has neither .spec_id nor .pattern_id — this function "
                "only knows those two trial-identifier field names; teach it the "
                "new one explicitly rather than guessing."
            )

        deflated = getattr(r, "deflated_sharpe", None)
        if deflated is None:
            raise ValueError(f"result {r!r} (trial_id={trial_id}) has no .deflated_sharpe")

        n_observations = getattr(r, "n_trading_days", None)
        if n_observations is None:
            raise ValueError(f"result {r!r} (trial_id={trial_id}) has no .n_trading_days")

        rows.append(
            CrossSectionalTrialResult(
                family_key=family_key,
                trial_id=str(trial_id),
                run_tag=run_tag,
                sharpe_annualized=float(r.sharpe_annualized),
                n_observations=int(n_observations),
                n_trials=int(deflated.n_trials),
                dsr=deflated.dsr,
                psr_vs_zero=deflated.psr_vs_zero,
                full_result_json=json.dumps(asdict(r), default=str),
            )
        )

    db.add_all(rows)
    db.commit()
    return len(rows)


def verify_persisted_trial_results(
    db: Session,
    run_tag: str,
    expected_rows: int,
    family_key: str | None = None,
) -> int:
    """Reads back what a run just wrote and RAISES if the count is wrong.

    Call this once, at the end of a research runner, after every
    persist_cross_sectional_trial_results() call for the run:

        written = 0
        for universe in summary.universes:
            written += persist_cross_sectional_trial_results(db, key, ..., run_tag=RUN_TAG)
        verify_persisted_trial_results(db, RUN_TAG, written)

    WHY A RUNNER CANNOT JUST TRUST THE WRITE. Two families — N-PORT
    flow-induced trading and the first tax-loss-selling run — left committed
    reports on disk describing results that no database row backs. There are
    two ways that happens, and this function covers both:

    * Wrong database. CONFIRMED, and reproduced against the pre-fix code on
      2026-09-06. app/config.py's sqlite default used to be a RELATIVE path,
      so a runner started from anywhere other than backend/ addressed an
      aladdin2.db that had never been migrated. SQLite creates a missing file
      instead of failing, so the run got all the way to commit before dying on
      "no such table". (Fixed at the source now — the default is absolute, and
      app.db's ensure_local_sqlite_schema() builds a schema for an empty
      SQLite file — but a check that only holds because two other things are
      working is not a check.) The row-count comparison below catches this.
    * Right database, doomed location. NOT confirmed for either family, and
      not ruled out for N-PORT, whose worktree was removed before anyone
      looked. A worktree-local aladdin2.db accepts every write happily and
      then disappears with the worktree at cleanup time; nothing raises, and
      the rows simply cease to exist later. A count check CANNOT see this,
      because at the moment of checking the rows really are there — which is
      why this function also logs the resolved file and shouts when it sits
      under .claude/worktrees/.

    Returns the read-back row count (which equals expected_rows, or this
    raised). Reads with a fresh SELECT rather than from the session's identity
    map so a broken commit cannot answer from memory.
    """
    if expected_rows <= 0:
        raise ValueError(
            f"verify_persisted_trial_results called with expected_rows={expected_rows} — "
            "a run that wrote nothing has nothing to verify, and calling this with 0 would "
            "make an empty database look like a success."
        )

    db.expire_all()
    stmt = (
        select(func.count())
        .select_from(CrossSectionalTrialResult)
        .where(CrossSectionalTrialResult.run_tag == run_tag)
    )
    if family_key is not None:
        stmt = stmt.where(CrossSectionalTrialResult.family_key == family_key)
    read_back = db.execute(stmt).scalar_one()

    where = describe_configured_database()
    if read_back != expected_rows:
        raise RuntimeError(
            f"PERSISTENCE CHECK FAILED: expected {expected_rows} rows for run_tag={run_tag!r}"
            + (f" family_key={family_key!r}" if family_key is not None else "")
            + f" but read back {read_back} from {where}. Any report files this run wrote are "
            "real; the database record is not. Do not treat this run as persisted."
        )

    logger.info(
        "persistence verified: %d rows for run_tag=%r read back from %s",
        read_back,
        run_tag,
        where,
    )
    warn_if_database_is_worktree_local()
    return read_back


def describe_configured_database() -> str:
    """The database the process is actually talking to, safe to log.

    A sqlite URL is a filesystem path and is shown in full — knowing WHICH
    aladdin2.db received a run's rows is the entire point. Anything else
    (Postgres) is reduced to its scheme, because those URLs carry credentials;
    refresh_family_inventory.py already redacts the same way.
    """
    from app.config import settings

    url = settings.database_url
    if url.startswith("sqlite"):
        return url
    return url.split("://", 1)[0] + "://<redacted>"


def warn_if_database_is_worktree_local() -> bool:
    """Logs a warning when the configured SQLite file lives inside a git
    worktree, and returns whether it did.

    Not an error: writing to a worktree-local database is a legitimate,
    already-accepted pattern in this project (most worktrees carry their own
    copy). It is only fatal when nobody notices before the worktree is
    removed, which is exactly what a warning at persistence time prevents.
    """
    from app.config import settings

    url = settings.database_url
    if not url.startswith("sqlite"):
        return False
    if ".claude/worktrees/" not in url:
        return False
    logger.warning(
        "THESE ROWS ARE IN A WORKTREE-LOCAL DATABASE: %s. Removing this worktree deletes "
        "them, and the committed report would be the only surviving record. Copy them into "
        "the main checkout's backend/aladdin2.db, or re-run with "
        "DATABASE_URL=sqlite:////abs/path/to/main/backend/aladdin2.db, before cleaning up.",
        url,
    )
    return True
