import logging
import threading
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)

_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Guards the one-time schema bootstrap below. Re-entrant because the bootstrap
# opens its own connections while holding it, and a plain Lock would deadlock
# if any of that re-entered on the same thread.
_schema_lock = threading.RLock()
_schema_ensured = False


def _stamp_alembic_head() -> None:
    """Records the current migration head in alembic_version after a
    create_all bootstrap, so the two ways of building this schema stay
    compatible in BOTH orders.

    Without this, a bootstrapped database has every table but an empty
    alembic_version, and the next `alembic upgrade head` replays the whole
    migration chain from base and dies on "table already exists". That is not
    a hypothetical: run_macro_beta.py carries a comment describing exactly
    that failure after an earlier unguarded create_all, and it is why this
    function exists rather than create_all standing alone.

    Reads the head via alembic's ScriptDirectory, which parses
    alembic/versions/ WITHOUT executing alembic/env.py — env.py imports this
    module, so running it from here would be circular.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    if not ini_path.exists():
        logger.warning(
            "bootstrapped a SQLite schema but found no alembic.ini at %s, so alembic_version "
            "was NOT stamped. A later `alembic upgrade head` against this file will fail on "
            "'table already exists'.",
            ini_path,
        )
        return

    heads = ScriptDirectory.from_config(Config(str(ini_path))).get_heads()
    if not heads:
        logger.warning("alembic reports no migration heads; alembic_version left empty")
        return

    with engine.begin() as conn:
        # Structurally the table alembic itself creates — same single
        # VARCHAR(32) NOT NULL column, same named primary-key constraint —
        # checked against the project database's own sqlite_master entry.
        # The stored DDL TEXT is not byte-identical: alembic renders it
        # across three lines with tab indentation and this renders it on one.
        # That is a formatting difference only; nothing reads this table's
        # DDL text, and alembic itself reads only version_num.
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version ("
                "version_num VARCHAR(32) NOT NULL, "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
            )
        )
        for head in heads:
            conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": head}
            )
    logger.info("stamped alembic_version with %s", ", ".join(heads))


def ensure_local_sqlite_schema() -> None:
    """Creates the full schema when — and only when — the configured database
    is a SQLite file that has NO tables at all.

    WHY THIS EXISTS. Every change in this project happens in a git worktree
    (CLAUDE.md rule 6.1), and aladdin2.db is gitignored, so a fresh worktree
    starts with no database. A research script run there computes a full
    backtest, writes its report files, and only then discovers at commit time
    that there is nowhere to put the rows: SQLite creates the missing file
    instead of refusing, so the failure lands on the INSERT, as
    "no such table: cross_sectional_trial_results", after the reports are
    already on disk. Reproduced against the pre-fix code on 2026-09-06;
    tests/test_db_schema_bootstrap.py pins it.

    Two families are known to have written committed reports with no matching
    database rows (N-PORT flow-induced trading, and the first tax-loss-selling
    run). The tax-loss-selling run hit exactly the failure above. N-PORT's
    worktree was removed before anyone looked, so which of the two
    worktree-database failures it hit — this one, or writing successfully into
    a worktree-local database that the cleanup then deleted — cannot now be
    determined. This function addresses the first; the second is only visible,
    not prevented, and cross_sectional_persistence.warn_if_database_is_worktree_local
    is what makes it visible.

    THREE GUARDS, all deliberate:

    * SQLITE ONLY. A postgresql:// URL returns immediately, before anything
      touches the network or the engine — production's schema is owned by
      `alembic upgrade head` in render.yaml's start command and nothing here
      may ever second-guess it.
    * EMPTY DATABASES ONLY. If the file has even one table this is a no-op.
      A half-migrated or hand-edited database is a human problem; silently
      adding tables to one would turn a visible error into an invisible
      divergence from the migration chain.
    * STAMPED. See _stamp_alembic_head — a bootstrapped schema records the
      migration head, so `alembic upgrade head` afterwards is a clean no-op
      instead of a crash.

    Called from SessionLocal() rather than at import time, which is what keeps
    it out of alembic's way entirely: alembic/env.py imports Base from this
    module but never opens a Session, so a migration run never triggers this
    and always exercises the real migration chain. It also means merely
    importing app.db does not create a stray database file — a property
    test_registration_scorecards.py already depends on.

    The create_all-vs-alembic equivalence was MEASURED, not assumed, on
    2026-09-06 against migration head b4e9d2c15a83: both routes produce the
    same 26 tables with identical column names, types, nullability and primary
    keys, and identical indexes. The differences are confined to SQL rendering
    — DEFAULT CURRENT_TIMESTAMP vs DEFAULT (CURRENT_TIMESTAMP), quoted table
    names, and column ORDER where a migration rebuilt a table in batch mode
    (alembic appends the added column, create_all puts it where the model
    does). None of that is visible through the ORM, which addresses columns by
    name. tests/test_db_schema_bootstrap.py re-runs the comparison so future
    drift fails a test instead of silently producing two different schemas
    depending on which route ran first.
    """
    global _schema_ensured
    if _schema_ensured:
        return
    with _schema_lock:
        if _schema_ensured:
            return

        if not engine.url.drivername.startswith("sqlite"):
            # Not SQLite: nothing to do, ever. Marked done so the check costs
            # one boolean per session for the rest of the process's life.
            _schema_ensured = True
            return

        existing = [t for t in inspect(engine).get_table_names() if not t.startswith("sqlite_")]
        if existing:
            _schema_ensured = True
            return

        # Imported HERE, not at module scope: every model module imports Base
        # from this module, so importing them at import time would be
        # circular. create_all only builds tables that are registered on
        # Base.metadata, so this import is what makes the bootstrap complete
        # rather than partial. (tests/conftest.py does the same thing for the
        # same reason.)
        import app.models  # noqa: F401 — registers every model on Base.metadata

        Base.metadata.create_all(bind=engine)
        _stamp_alembic_head()
        logger.warning(
            "created a fresh SQLite schema in the previously-empty database %s. Rows written "
            "from here live ONLY in that file — if it is inside a git worktree, removing the "
            "worktree destroys them.",
            engine.url.database,
        )
        _schema_ensured = True


def SessionLocal() -> Session:
    """Opens a Session against the configured database.

    Deliberately a function rather than the bare `sessionmaker` it used to be:
    this is the single choke point every caller in the codebase already goes
    through (routers via get_db, background runners and research scripts
    directly), so it is the one place a schema guarantee can be installed
    without touching ~200 call sites or threading a setup step into every
    research runner. The call signature is unchanged — SessionLocal() still
    returns a Session and nothing accesses sessionmaker-specific attributes on
    it.
    """
    ensure_local_sqlite_schema()
    return _session_factory()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
