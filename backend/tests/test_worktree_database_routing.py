"""Tests for the second half of the "a research run's rows went nowhere" fix
(2026-09-06): the DEFAULT sqlite database is ONE physical file, addressed
identically from the main checkout and from every linked git worktree, and
that file is safe for more than one process to write at a time.

THE BUG BEING CLOSED. Every change in this project happens in a worktree
(CLAUDE.md rule 6.1) and aladdin2.db is gitignored, so each worktree's own
copy of app/config.py used to resolve to that worktree's own physical
database. A backtest run there wrote real trial rows, verified them, and
reported success — then `git worktree remove` deleted the directory and the
rows with it. Two families had to be hand-migrated with
`sqlite3 ATTACH DATABASE ... INSERT ... SELECT` before cleanup, both times
only because somebody remembered to.

THE BUG THIS MUSTN'T INTRODUCE. Once every checkout shares one file, two
genuinely separate OS processes (a `uvicorn --reload` from main and a
research script inside a worktree) become ordinary concurrent writers of the
same SQLite file. The last section here demonstrates that the pragma-less
engine app/db.py used to build really does fail that with
"database is locked", and that the current one does not.

Like tests/test_db_schema_bootstrap.py, the end-to-end parts run in
SUBPROCESSES: app.db builds its engine at import time from
app.config.settings, so "what happens with a different DATABASE_URL" is only
honestly testable by starting a process with that environment.
"""

import os
import shutil
import sqlite3
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from app.config import (
    BACKEND_DIR,
    DEFAULT_SQLITE_URL,
    MAIN_CHECKOUT_BACKEND_DIR,
    _git_common_dir,
    _main_checkout_backend_dir,
)
from app.db import SQLITE_BUSY_TIMEOUT_MS

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="these tests exercise real git worktree resolution"
)


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )


def _make_repo_with_a_linked_worktree(tmp_path: Path) -> tuple[Path, Path]:
    """A REAL git repository with a REAL linked worktree, shaped like this
    project (backend/app/config.py present so the resolver's sanity guard is
    satisfied). Returns (main checkout root, linked worktree root).

    Real git rather than a hand-built .git file: the whole point of the code
    under test is that it reads what git actually reports, and a fabricated
    fixture would be testing the fabrication.
    """
    main = tmp_path / "mainrepo"
    (main / "backend" / "app").mkdir(parents=True)
    (main / "backend" / "app" / "config.py").write_text("# stand-in for app/config.py\n")

    _git("init", "-b", "main", cwd=main)
    _git("config", "user.email", "test@example.invalid", cwd=main)
    _git("config", "user.name", "test", cwd=main)
    # Explicit path, never `git add -A` (CLAUDE.md rule 4). --no-verify so a
    # globally-configured core.hooksPath cannot make this fixture fail.
    _git("add", "backend/app/config.py", cwd=main)
    _git("commit", "--no-verify", "-m", "init", cwd=main)

    worktree = tmp_path / "linked" / "feature"
    (worktree.parent).mkdir(parents=True, exist_ok=True)
    _git("worktree", "add", "-b", "feature", str(worktree), cwd=main)
    return main, worktree


# --------------------------------------------------------------------------
# 1. Resolution: one file from every checkout
# --------------------------------------------------------------------------


def test_a_linked_worktree_resolves_to_the_main_checkouts_backend(tmp_path):
    """THE regression test for the routing change, against real git.

    Before this, the worktree's own backend/ was the answer, and the database
    written there died with the worktree.
    """
    main, worktree = _make_repo_with_a_linked_worktree(tmp_path)

    resolved = _main_checkout_backend_dir(worktree / "backend")

    assert resolved == (main / "backend").resolve()
    assert resolved != (worktree / "backend").resolve()


def test_the_main_checkout_resolves_to_itself(tmp_path):
    """The other half: nothing moves for anyone not working in a worktree.
    Idempotence is the property that matters — resolving the main checkout's
    backend/ must return that same directory, not a neighbour of it.
    """
    main, _ = _make_repo_with_a_linked_worktree(tmp_path)
    assert _main_checkout_backend_dir(main / "backend") == (main / "backend").resolve()


def test_this_checkouts_own_resolution_is_stable():
    """Against the repository the suite is actually running from, whichever
    that is: re-resolving an already-resolved answer must be a fixed point.
    Run from the main checkout this also asserts BACKEND_DIR is unchanged,
    since the two are then the same directory."""
    assert _main_checkout_backend_dir(MAIN_CHECKOUT_BACKEND_DIR) == MAIN_CHECKOUT_BACKEND_DIR


def test_git_common_dir_is_the_shared_one_not_the_worktree_specific_one(tmp_path):
    """The single easiest way to get this wrong is `--git-dir`, which in a
    linked worktree answers <main>/.git/worktrees/<name>. `--git-common-dir`
    is the shared directory, and it is what the code asks for."""
    main, worktree = _make_repo_with_a_linked_worktree(tmp_path)

    common = _git_common_dir(worktree / "backend")
    assert common == (main / ".git").resolve()

    worktree_specific = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-dir"],
        cwd=str(worktree / "backend"),
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    ).stdout.strip()
    assert Path(worktree_specific).resolve() != common, (
        "--git-dir and --git-common-dir agreed, so this fixture is not exercising "
        "a real linked worktree and the distinction is untested"
    )


# --------------------------------------------------------------------------
# 2. Fallbacks — every one of them lands on exactly the old behaviour
# --------------------------------------------------------------------------


def test_git_missing_falls_back_to_the_this_file_relative_directory(monkeypatch):
    """The stripped-production-container case. Nothing about a missing git
    may raise out of an import, and the answer must be exactly what the code
    computed before this change."""
    import app.config as config_module

    def _no_git(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory: 'git'")

    monkeypatch.setattr(config_module.subprocess, "run", _no_git)
    assert _main_checkout_backend_dir(BACKEND_DIR) == BACKEND_DIR
    assert _git_common_dir(BACKEND_DIR) is None


def test_a_git_timeout_falls_back(monkeypatch):
    import app.config as config_module

    def _hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=config_module._GIT_PROBE_TIMEOUT_SECONDS)

    monkeypatch.setattr(config_module.subprocess, "run", _hang)
    assert _main_checkout_backend_dir(BACKEND_DIR) == BACKEND_DIR


def test_not_a_git_repository_falls_back(monkeypatch):
    """Both spellings exit non-zero — which is also what an ancient git does
    to `--path-format` and what any git does outside a repository."""
    import app.config as config_module

    calls = []

    def _fails(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 128, "", "fatal: not a git repository")

    monkeypatch.setattr(config_module.subprocess, "run", _fails)
    assert _main_checkout_backend_dir(BACKEND_DIR) == BACKEND_DIR
    assert len(calls) == 2, "the plain --git-common-dir spelling was not tried as a fallback"


def test_a_git_answer_that_is_not_this_project_falls_back(tmp_path, monkeypatch):
    """A bare repository (/path/to/repo.git), or a redirected GIT_COMMON_DIR,
    makes <common>/.. something that is not a checkout at all. Requiring
    app/config.py to exist under the candidate keeps those on the old path
    instead of silently naming a database in a stranger's directory."""
    import app.config as config_module

    bare = tmp_path / "somewhere" / "repo.git"
    bare.mkdir(parents=True)

    def _answers_bare(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, str(bare) + "\n", "")

    monkeypatch.setattr(config_module.subprocess, "run", _answers_bare)
    assert _main_checkout_backend_dir(BACKEND_DIR) == BACKEND_DIR


def test_a_relative_git_answer_is_resolved_against_the_probed_directory(tmp_path, monkeypatch):
    """`--path-format` needs git 2.31+. Without it, plain `--git-common-dir`
    answers RELATIVELY from a main checkout (".git", "../.git"), and relative
    to WHAT is the trap: it is relative to the directory git ran in, not to
    the calling process's working directory. This forces the old-git path by
    failing the `--path-format` spelling, then runs from an unrelated cwd.
    """
    import app.config as config_module

    main, _ = _make_repo_with_a_linked_worktree(tmp_path)
    real_run = subprocess.run

    def _pretend_path_format_is_unsupported(cmd, **kwargs):
        if "--path-format=absolute" in cmd:
            return subprocess.CompletedProcess(cmd, 129, "", "unknown option `path-format'")
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(config_module.subprocess, "run", _pretend_path_format_is_unsupported)
    # Somewhere that is NOT the repository: if the code resolved against the
    # process cwd instead of the probed directory, this is where it would go
    # wrong.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert _git_common_dir(main / "backend") == (main / ".git").resolve()
    assert _main_checkout_backend_dir(main / "backend") == (main / "backend").resolve()


# --------------------------------------------------------------------------
# 3. The worktree-local warning still means something
# --------------------------------------------------------------------------


def test_the_default_database_is_not_inside_a_worktree():
    """warn_if_database_is_worktree_local() string-matches ".claude/worktrees/"
    in the resolved URL. The point of the routing change is that the DEFAULT
    can no longer produce such a URL — from any checkout, including whichever
    one is running this."""
    assert ".claude/worktrees/" not in DEFAULT_SQLITE_URL


def test_an_explicit_worktree_override_is_still_flagged(monkeypatch, caplog):
    """The one case where the warning still carries information: somebody
    deliberately pointed DATABASE_URL at a worktree-local file. That is a
    supported thing to want — it is the documented escape hatch — and it is
    still the thing that loses rows at cleanup time if nobody notices.
    """
    import logging

    from app.config import settings as live_settings
    from app.services.research_lab.cross_sectional_persistence import (
        warn_if_database_is_worktree_local,
    )

    override = "sqlite:////repo/.claude/worktrees/some-branch/backend/aladdin2.db"
    monkeypatch.setattr(live_settings, "database_url", override)
    with caplog.at_level(logging.WARNING):
        assert warn_if_database_is_worktree_local() is True
    assert "WORKTREE-LOCAL DATABASE" in caplog.text


def test_the_real_default_url_is_not_flagged(monkeypatch):
    from app.config import settings as live_settings
    from app.services.research_lab.cross_sectional_persistence import (
        warn_if_database_is_worktree_local,
    )

    monkeypatch.setattr(live_settings, "database_url", DEFAULT_SQLITE_URL)
    assert warn_if_database_is_worktree_local() is False


# --------------------------------------------------------------------------
# 4. Concurrency — the new failure mode this change could have introduced
# --------------------------------------------------------------------------


def _run(code: str, *, cwd: Path, argv: list[str] | None = None, env_extra: dict | None = None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(BACKEND_DIR)
    env.pop("DATABASE_URL", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code), *(argv or [])],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def test_a_sqlite_connection_gets_wal_and_a_busy_timeout(tmp_path):
    """Both pragmas, read back off a real connection opened the way every
    caller in the codebase opens one (SessionLocal)."""
    db_path = tmp_path / "pragmas.db"
    proc = _run(
        """
        from sqlalchemy import text
        from app.db import SessionLocal

        db = SessionLocal()
        try:
            print("JOURNAL", db.execute(text("pragma journal_mode")).scalar())
            print("BUSY", db.execute(text("pragma busy_timeout")).scalar())
        finally:
            db.close()
        """,
        cwd=tmp_path,
        env_extra={"DATABASE_URL": f"sqlite:///{db_path}"},
    )
    assert proc.returncode == 0, f"STDOUT\n{proc.stdout}\nSTDERR\n{proc.stderr}"
    assert "JOURNAL wal" in proc.stdout, proc.stdout
    assert f"BUSY {SQLITE_BUSY_TIMEOUT_MS}" in proc.stdout, proc.stdout


def test_a_postgres_url_installs_no_sqlite_pragma_handler(tmp_path):
    """The pragma handler is guarded exactly the way connect_args already was,
    so a Postgres URL never even DEFINES it. Proven WITHOUT a Postgres server,
    the same way
    test_db_schema_bootstrap.test_schema_bootstrap_never_runs_for_a_postgres_url
    is: the port has nothing listening, so a handler that fired would have to
    connect and would raise. Importing cleanly is the proof."""
    workdir = tmp_path / "pg"
    workdir.mkdir()
    proc = _run(
        """
        import app.db as appdb

        assert appdb.engine.url.drivername == "postgresql+psycopg", appdb.engine.url
        print("HANDLER", hasattr(appdb, "_apply_sqlite_concurrency_pragmas"))
        """,
        cwd=workdir,
        env_extra={"DATABASE_URL": "postgres://u:p@127.0.0.1:1/nope"},
    )
    assert proc.returncode == 0, f"STDOUT\n{proc.stdout}\nSTDERR\n{proc.stderr}"
    assert "HANDLER False" in proc.stdout, proc.stdout


# One writer. Holds a write transaction open across many INSERTs so the two
# copies of it genuinely overlap instead of politely taking turns. `mode`
# selects the engine: "app" is app/db.py's real engine (pragma handler
# installed), "bare" is a create_engine call identical to the line app/db.py
# had before this change — it sets no pragmas of its own, so journal mode and
# busy timeout are whatever SQLite and the driver default to.
_WRITER = """
    import sys
    import time

    from sqlalchemy import create_engine, text

    url, mode, start_at, tag, n_rows, hold_step = sys.argv[1:7]
    start_at, n_rows, hold_step = float(start_at), int(n_rows), float(hold_step)

    if mode == "app":
        import app.db as appdb
        engine = appdb.engine
    else:
        engine = create_engine(url, connect_args={"check_same_thread": False})

    # Barrier: both writers open their transaction at the same wall clock
    # instant, so the overlap is not a matter of luck.
    while time.time() < start_at:
        time.sleep(0.005)

    with engine.begin() as conn:
        for i in range(n_rows):
            conn.execute(
                text("insert into concurrency_probe (writer, i) values (:w, :i)"),
                {"w": tag, "i": i},
            )
            time.sleep(hold_step)
    print("WROTE", tag)
"""

# The contention window has to straddle the baseline being disproved. MEASURED
# on 2026-09-06 (Python 3.12, SQLite 3.53.4): a bare
# create_engine("sqlite:///...") reports busy_timeout=5000, because Python's
# sqlite3 driver passes its documented `timeout=5.0`. So a writer must hold
# the lock for MORE than 5s for the pragma-less engine to fail, and less than
# SQLITE_BUSY_TIMEOUT_MS (30s) for the real one to survive. 13 x 0.5s = 6.5s
# sits between them, and every source of slowness lengthens the hold while
# leaving the 5s deadline fixed — so a slow machine makes the pragma-less case
# fail HARDER, never accidentally pass.
_ROWS_PER_WRITER = 13
_HOLD_STEP_SECONDS = 0.5


def _probe_db(tmp_path: Path, name: str) -> Path:
    """A database holding one trivial table, created by plain sqlite3 so the
    FILE starts in SQLite's own default rollback-journal mode — i.e. exactly
    what a first run finds. (The busy timeout is a per-connection setting, not
    a property of the file, so it is not established here.)"""
    db_path = tmp_path / name
    conn = sqlite3.connect(db_path)
    conn.execute("create table concurrency_probe (writer text, i integer)")
    conn.commit()
    conn.close()
    return db_path


def _launch_two_writers(tmp_path: Path, db_path: Path, mode: str):
    url = f"sqlite:///{db_path}"
    start_at = time.time() + 2.0
    env = dict(os.environ)
    env["PYTHONPATH"] = str(BACKEND_DIR)
    env["DATABASE_URL"] = url
    procs = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                textwrap.dedent(_WRITER),
                url,
                mode,
                str(start_at),
                tag,
                str(_ROWS_PER_WRITER),
                str(_HOLD_STEP_SECONDS),
            ],
            cwd=str(tmp_path),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for tag in ("A", "B")
    ]
    return [(p, *p.communicate(timeout=180)) for p in procs]


def test_two_concurrent_processes_can_both_write_the_same_sqlite_file(tmp_path):
    """The scenario this change creates: a uvicorn from main and a research
    script from a worktree, now genuinely writing one file at once. Both must
    finish, and every row must land."""
    db_path = _probe_db(tmp_path, "shared.db")
    results = _launch_two_writers(tmp_path, db_path, mode="app")

    for proc, out, err in results:
        assert proc.returncode == 0, f"a writer failed:\nSTDOUT\n{out}\nSTDERR\n{err}"
        assert "WROTE" in out

    conn = sqlite3.connect(db_path)
    total = conn.execute("select count(*) from concurrency_probe").fetchone()[0]
    per_writer = dict(
        conn.execute("select writer, count(*) from concurrency_probe group by writer")
    )
    journal = conn.execute("pragma journal_mode").fetchone()[0]
    conn.close()

    assert total == 2 * _ROWS_PER_WRITER, per_writer
    assert per_writer == {"A": _ROWS_PER_WRITER, "B": _ROWS_PER_WRITER}
    assert journal.lower() == "wal", journal


def test_the_same_two_writers_fail_without_the_pragmas(tmp_path):
    """Proof that the pragma is load-bearing and the failure mode is real, not
    hypothetical. Identical writers, identical timing, against an engine built
    exactly the way app/db.py built its one before this change.

    The baseline is the driver's own 5-second wait, not zero (see the comment
    on _ROWS_PER_WRITER — measured, not assumed). The writers hold the lock
    for 6.5s, so the pragma-less loser runs out of patience and raises
    "database is locked" while the 30s one above waits and completes.

    If this test ever stops failing, the test above has stopped proving
    anything and both should be re-examined rather than trusted.
    """
    db_path = _probe_db(tmp_path, "unprotected.db")
    results = _launch_two_writers(tmp_path, db_path, mode="bare")

    failures = [(out, err) for proc, out, err in results if proc.returncode != 0]
    assert failures, (
        "both pragma-less writers succeeded, so this test is no longer "
        "demonstrating the failure the pragmas prevent"
    )
    assert any("database is locked" in err for _, err in failures), [
        err for _, err in failures
    ]
