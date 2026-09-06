"""Tests for the two halves of the "a research run's rows went nowhere" fix:

  1. app/config.py's SQLite default is ABSOLUTE and anchored to backend/,
     so which database a process talks to no longer depends on where it was
     started from.
  2. app/db.py's ensure_local_sqlite_schema() builds the schema for an EMPTY
     SQLite file, so a fresh git worktree can persist results instead of
     dying on "no such table" after the reports are already written.

Most of these run the real thing in a SUBPROCESS rather than poking at
already-imported module globals. app.db builds its engine at import time from
app.config.settings, so the only honest way to test "what happens with a
different DATABASE_URL / a different working directory" is to start a process
with that environment — an importlib.reload() dance would be testing a
re-imported hybrid, not the code path a research runner actually takes.
"""

import json
import os
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from app.config import (
    BACKEND_DIR,
    DEFAULT_SQLITE_URL,
    MAIN_CHECKOUT_BACKEND_DIR,
    Settings,
    settings,
)

# The literal that used to be app/config.py's database_url default. Kept here
# so the "resolves to the same file" test compares against the real historical
# value rather than a paraphrase of it.
OLD_RELATIVE_DEFAULT = "sqlite:///./aladdin2.db"


def _run(code: str, *, cwd: Path, env_extra: dict[str, str] | None = None):
    """Runs `code` in a fresh interpreter with `app` resolved from THIS
    checkout (PYTHONPATH=BACKEND_DIR beats the editable install, which points
    at whichever checkout ran `pip install -e .`)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(BACKEND_DIR)
    env.pop("DATABASE_URL", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def _ok(proc) -> str:
    assert proc.returncode == 0, f"subprocess failed:\nSTDOUT\n{proc.stdout}\nSTDERR\n{proc.stderr}"
    return proc.stdout


# --------------------------------------------------------------------------
# 1. The default URL
# --------------------------------------------------------------------------


def test_default_sqlite_url_is_absolute_and_points_at_backend_aladdin2_db():
    database = make_url(DEFAULT_SQLITE_URL).database
    assert database is not None
    path = Path(database)
    assert path.is_absolute(), f"{DEFAULT_SQLITE_URL} is not absolute"
    # MAIN_CHECKOUT_BACKEND_DIR, not BACKEND_DIR: since 2026-09-06 the default
    # is anchored to the main checkout's backend/ so that a run inside a linked
    # worktree writes to a database that outlives `git worktree remove`. The
    # two are the same directory whenever this runs from the main checkout.
    # See tests/test_worktree_database_routing.py for that routing itself.
    assert path == MAIN_CHECKOUT_BACKEND_DIR / "aladdin2.db"


def test_new_default_names_the_same_file_the_old_relative_default_named():
    """The whole point of the change is that NOTHING moves for the normal
    `cd backend && uvicorn ...` / `cd backend && pytest` workflow.

    A relative sqlite path is resolved by the process working directory, so
    "what the old default meant when run from backend/" is exactly
    <that checkout's backend>/<the relative part>. If these two ever stop
    matching, the change silently relocated the developer database.

    Anchored to MAIN_CHECKOUT_BACKEND_DIR: from the main checkout that is
    BACKEND_DIR and this is the identical assertion it has always been. From
    a linked worktree the two differ ON PURPOSE — that divergence is the
    2026-09-06 routing change and is pinned in
    tests/test_worktree_database_routing.py — and what this test still
    guarantees is that the file the default names is the one the historical
    `cd backend && ...` workflow has always meant.
    """
    old_relative = make_url(OLD_RELATIVE_DEFAULT).database
    assert old_relative is not None
    old_resolved_from_backend = (MAIN_CHECKOUT_BACKEND_DIR / old_relative).resolve()
    new_resolved = Path(make_url(DEFAULT_SQLITE_URL).database).resolve()
    assert old_resolved_from_backend == new_resolved


def _database_url_is_configured_explicitly() -> bool:
    """True when this checkout overrides the default — via the environment,
    or via a backend/.env entry (pydantic-settings reads .env relative to the
    working directory, which under pytest is backend/)."""
    if os.environ.get("DATABASE_URL"):
        return True
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return False
    return any(
        line.strip().startswith("DATABASE_URL=")
        for line in env_file.read_text().splitlines()
    )


def test_settings_default_is_the_absolute_url():
    """And it survives Settings() construction — a field_validator that
    rewrote the sqlite default would defeat the whole change."""
    if _database_url_is_configured_explicitly():
        pytest.skip("DATABASE_URL is set explicitly in this checkout; the default is overridden")
    assert settings.database_url == DEFAULT_SQLITE_URL


def test_configured_database_does_not_depend_on_the_working_directory(tmp_path):
    """The actual regression: start a process from somewhere that is NOT
    backend/ and confirm it still resolves the same database file.

    Under the old relative default this printed <cwd>/aladdin2.db — a file
    that had never been migrated — and every INSERT from such a process died
    on "no such table" AFTER the run's reports had been written.

    Imports app.config only, never app.db, so nothing is created anywhere.
    """
    out = _ok(
        _run(
            """
            from app.config import settings
            print(settings.database_url)
            """,
            cwd=tmp_path,
        )
    ).strip()
    assert out == DEFAULT_SQLITE_URL
    assert Path(make_url(out).database) == MAIN_CHECKOUT_BACKEND_DIR / "aladdin2.db"


# --------------------------------------------------------------------------
# 2. Postgres is untouched
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "given,expected",
    [
        ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgresql://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgresql+psycopg://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
    ],
)
def test_postgres_urls_are_normalized_exactly_as_before(given, expected):
    """_normalize_postgres_scheme is production's path (render.yaml sets
    DATABASE_URL explicitly, `sync: false`) and must be untouched by the
    SQLite-default change."""
    assert Settings(database_url=given).database_url == expected


def test_a_sqlite_url_passed_in_explicitly_is_passed_through_verbatim():
    explicit = "sqlite:////tmp/somewhere/else.db"
    assert Settings(database_url=explicit).database_url == explicit


def test_schema_bootstrap_never_runs_for_a_postgres_url(tmp_path):
    """The guard proven WITHOUT a Postgres server: the URL points at a port
    nothing is listening on, so any attempt to connect would raise
    OperationalError. ensure_local_sqlite_schema() returning cleanly is proof
    it never entered the SQLite path, and SessionLocal() succeeding is proof
    the guarantee is not smuggled in somewhere else.
    """
    # Its own directory: tmp_path itself already holds conftest's test.db.
    workdir = tmp_path / "postgres_run"
    workdir.mkdir()
    out = _ok(
        _run(
            """
            from app.config import settings
            from app.db import SessionLocal, engine, ensure_local_sqlite_schema

            assert settings.database_url.startswith("postgresql+psycopg://"), settings.database_url
            assert engine.url.drivername == "postgresql+psycopg", engine.url.drivername
            assert not engine.url.drivername.startswith("sqlite")

            ensure_local_sqlite_schema()   # must be a silent no-op, not a connect
            db = SessionLocal()            # must not connect either
            db.close()
            print("NO_CONNECT_ATTEMPTED")
            """,
            cwd=workdir,
            env_extra={"DATABASE_URL": "postgres://u:p@127.0.0.1:1/nope"},
        )
    )
    assert "NO_CONNECT_ATTEMPTED" in out
    assert not list(workdir.iterdir()), f"a Postgres run created files: {list(workdir.iterdir())}"


# --------------------------------------------------------------------------
# 3. The fresh-worktree scenario
# --------------------------------------------------------------------------

_WRITE_A_TRIAL_ROW = """
    from app.db import SessionLocal
    from app.models.cross_sectional_trial_result import CrossSectionalTrialResult

    db = SessionLocal()
    try:
        db.add(
            CrossSectionalTrialResult(
                family_key="bootstrap_probe",
                trial_id="t1",
                run_tag="bootstrap_probe_run",
                sharpe_annualized=0.5,
                n_observations=100,
                n_trials=1,
                dsr=0.4,
                psr_vs_zero=0.6,
                full_result_json="{}",
            )
        )
        db.commit()
        print("ROWS", db.query(CrossSectionalTrialResult).count())
    finally:
        db.close()
"""


def test_fresh_database_gets_a_schema_and_a_write_actually_lands(tmp_path):
    """THE regression test. A brand-new SQLite path — the state every fresh
    git worktree starts in, since aladdin2.db is gitignored — must end up with
    a real schema and a real committed row.

    Before the fix this subprocess died with
    "sqlite3.OperationalError: no such table: cross_sectional_trial_results".
    """
    db_path = tmp_path / "fresh.db"
    assert not db_path.exists()

    out = _ok(
        _run(_WRITE_A_TRIAL_ROW, cwd=tmp_path, env_extra={"DATABASE_URL": f"sqlite:///{db_path}"})
    )
    assert "ROWS 1" in out
    assert db_path.exists()

    # Read it back from a plain sqlite3 connection: the row must be in the
    # FILE, not merely in a session that reported success.
    conn = sqlite3.connect(db_path)
    assert conn.execute(
        "select count(*) from cross_sectional_trial_results where family_key='bootstrap_probe'"
    ).fetchone()[0] == 1
    conn.close()


def test_a_bootstrapped_database_is_stamped_at_the_alembic_head(tmp_path):
    """Otherwise the fix would trade one failure for another: a schema built
    outside Alembic with an empty alembic_version makes the very next
    `alembic upgrade head` replay from base and die on "table already exists".
    run_macro_beta.py documents that exact failure from an earlier unguarded
    create_all, which is why the bootstrap stamps.
    """
    db_path = tmp_path / "fresh.db"
    _ok(_run(_WRITE_A_TRIAL_ROW, cwd=tmp_path, env_extra={"DATABASE_URL": f"sqlite:///{db_path}"}))

    conn = sqlite3.connect(db_path)
    stamped = [r[0] for r in conn.execute("select version_num from alembic_version")]
    conn.close()

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    heads = ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini"))).get_heads()
    assert sorted(stamped) == sorted(heads)


def test_alembic_upgrade_head_is_a_clean_no_op_on_a_bootstrapped_database(tmp_path):
    """The other half of the same guarantee, end to end: after a bootstrap,
    the documented setup command must still succeed."""
    db_path = tmp_path / "fresh.db"
    _ok(_run(_WRITE_A_TRIAL_ROW, cwd=tmp_path, env_extra={"DATABASE_URL": f"sqlite:///{db_path}"}))

    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["PYTHONPATH"] = str(BACKEND_DIR)
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 0, f"STDOUT\n{proc.stdout}\nSTDERR\n{proc.stderr}"
    # And the probe row is still there — no migration rebuilt the table.
    conn = sqlite3.connect(db_path)
    assert conn.execute("select count(*) from cross_sectional_trial_results").fetchone()[0] == 1
    conn.close()


def test_importing_app_db_does_not_create_a_database_file(tmp_path):
    """The bootstrap hangs off SessionLocal(), never off import, for two
    reasons: alembic/env.py imports this module and must keep exercising the
    real migration chain, and test_registration_scorecards.py relies on a bare
    import not littering a stray aladdin2.db into every worktree and CI
    checkout (a failure it observed for real).
    """
    db_path = tmp_path / "never.db"
    _ok(
        _run(
            """
            import app.db
            print("IMPORTED", app.db.engine.url)
            """,
            cwd=tmp_path,
            env_extra={"DATABASE_URL": f"sqlite:///{db_path}"},
        )
    )
    assert not db_path.exists(), "importing app.db created a database file"


def test_bootstrap_refuses_to_touch_a_database_that_already_has_tables(tmp_path):
    """Empty databases only. A half-migrated or hand-edited file is a human
    problem; quietly adding tables to one would turn a visible error into an
    invisible divergence from the migration chain.
    """
    db_path = tmp_path / "partial.db"
    conn = sqlite3.connect(db_path)
    conn.execute("create table something_unrelated (x integer)")
    conn.commit()
    conn.close()

    proc = _run(
        """
        from app.db import SessionLocal
        db = SessionLocal()
        db.close()
        print("OPENED")
        """,
        cwd=tmp_path,
        env_extra={"DATABASE_URL": f"sqlite:///{db_path}"},
    )
    assert proc.returncode == 0, proc.stderr

    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
    conn.close()
    assert tables == {"something_unrelated"}, tables


def test_an_already_populated_database_is_left_exactly_as_it_was(tmp_path):
    """The normal existing workflow: a real, migrated, populated aladdin2.db
    opened the usual way must behave identically to before — same schema, same
    rows, nothing rebuilt.
    """
    db_path = tmp_path / "existing.db"
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["PYTHONPATH"] = str(BACKEND_DIR)
    migrate = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert migrate.returncode == 0, f"STDOUT\n{migrate.stdout}\nSTDERR\n{migrate.stderr}"

    conn = sqlite3.connect(db_path)
    conn.execute(
        "insert into cross_sectional_trial_results "
        "(family_key, trial_id, run_tag, sharpe_annualized, n_observations, n_trials, "
        " full_result_json) values ('pre_existing','t0','r0',1.0,10,1,'{}')"
    )
    conn.commit()
    before = {r[0]: r[1] for r in conn.execute("select name, sql from sqlite_master")}
    conn.close()

    _ok(_run(_WRITE_A_TRIAL_ROW, cwd=tmp_path, env_extra={"DATABASE_URL": f"sqlite:///{db_path}"}))

    conn = sqlite3.connect(db_path)
    after = {r[0]: r[1] for r in conn.execute("select name, sql from sqlite_master")}
    survived = conn.execute(
        "select count(*) from cross_sectional_trial_results where family_key='pre_existing'"
    ).fetchone()[0]
    conn.close()
    assert after == before, "the schema changed under an already-migrated database"
    assert survived == 1, "a pre-existing row did not survive"


# --------------------------------------------------------------------------
# 4. create_all and alembic must keep agreeing
# --------------------------------------------------------------------------


def _structure(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    tables = sorted(
        r[0]
        for r in conn.execute("select name from sqlite_master where type='table'")
        if not r[0].startswith("sqlite_") and r[0] != "alembic_version"
    )
    out = {"tables": tables, "columns": {}, "indexes": {}}
    for t in tables:
        # (name, type, notnull, pk) — deliberately NOT ordinal position:
        # alembic's batch-mode table rebuilds append columns at the end, which
        # is a rendering difference, not a schema difference.
        out["columns"][t] = sorted(
            (r[1], r[2].upper(), r[3], r[5]) for r in conn.execute(f'pragma table_info("{t}")')
        )
    out["indexes"] = sorted(
        (r[0], r[1])
        for r in conn.execute(
            "select name, tbl_name from sqlite_master where type='index' "
            "and name not like 'sqlite_%'"
        )
    )
    conn.close()
    return out


def test_create_all_and_alembic_produce_the_same_schema(tmp_path):
    """The bootstrap uses Base.metadata.create_all while production and the
    documented local setup use `alembic upgrade head`. That is only safe while
    the two agree, so this measures it instead of assuming it.

    Measured equal on 2026-09-06: same 26 tables, same columns (name, type,
    nullability, primary key), same indexes. If a model is ever changed
    without a matching migration (or vice versa) this fails here rather than
    producing two different schemas depending on which route ran first.
    """
    ca_db = tmp_path / "create_all.db"
    al_db = tmp_path / "alembic.db"

    _ok(
        _run(
            """
            import app.models  # noqa: F401
            from app.db import Base, engine
            Base.metadata.create_all(bind=engine)
            """,
            cwd=tmp_path,
            env_extra={"DATABASE_URL": f"sqlite:///{ca_db}"},
        )
    )

    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{al_db}"
    env["PYTHONPATH"] = str(BACKEND_DIR)
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 0, f"STDOUT\n{proc.stdout}\nSTDERR\n{proc.stderr}"

    ca = _structure(ca_db)
    al = _structure(al_db)
    assert ca["tables"] == al["tables"], json.dumps(
        {
            "only_create_all": sorted(set(ca["tables"]) - set(al["tables"])),
            "only_alembic": sorted(set(al["tables"]) - set(ca["tables"])),
        }
    )
    assert ca["indexes"] == al["indexes"]
    for table in ca["tables"]:
        assert ca["columns"][table] == al["columns"][table], (
            f"column drift in {table}: "
            f"only create_all={sorted(set(ca['columns'][table]) - set(al['columns'][table]))} "
            f"only alembic={sorted(set(al['columns'][table]) - set(ca['columns'][table]))}"
        )
