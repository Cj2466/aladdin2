"""The pre-commit hook that refuses a direct commit on `main`.

Tested against REAL git in a throwaway repository rather than by reading the
script, because the property that actually matters is not "does the shell
logic look right" but "does git invoke this hook in the situations we think
it does". Specifically: this project lands verified work with a merge commit
made while HEAD is main, and a hook that blocked that would break the exact
workflow it exists to protect. Whether `git merge` reaches pre-commit at all
is a fact about git, not about the script, so it is measured here.

The hook under test is the tracked one at .githooks/pre-commit — the same
file `.githooks/install.sh` points core.hooksPath at, not a copy.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / ".githooks" / "pre-commit"


def git(*args, cwd, check=True, env=None):
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        env=full_env,
    )


@pytest.fixture
def repo(tmp_path):
    """A throwaway repo on `main` with the tracked hook installed exactly the
    way install.sh installs it (core.hooksPath), and one initial commit."""
    root = tmp_path / "repo"
    root.mkdir()
    git("init", "-q", "-b", "main", cwd=root)
    git("config", "user.email", "test@example.invalid", cwd=root)
    git("config", "user.name", "Hook Test", cwd=root)

    hooks_dir = root / ".githooks"
    hooks_dir.mkdir()
    shutil.copy2(HOOK, hooks_dir / "pre-commit")
    (hooks_dir / "pre-commit").chmod(0o755)
    git("config", "core.hooksPath", ".githooks", cwd=root)

    (root / "seed.txt").write_text("seed\n")
    git("add", "seed.txt", cwd=root)
    # The seed commit itself is on main, so it needs the override — which
    # incidentally proves the override works before anything else is tested.
    git("commit", "-q", "-m", "seed", cwd=root, env={"ALLOW_MAIN_COMMIT": "1"})
    return root


def _write_and_stage(repo: Path, name: str, text: str) -> None:
    (repo / name).write_text(text)
    git("add", name, cwd=repo)


def test_hook_file_is_executable_and_tracked():
    assert HOOK.exists(), f"{HOOK} is missing — the tracked hook is the deliverable"
    # git will not run a non-executable hook and says nothing when it skips one,
    # so the committed MODE is load-bearing: install.sh chmods it, but a fresh
    # clone must not depend on that having been run.
    assert os.access(HOOK, os.X_OK), f"{HOOK} is not executable (committed mode must be 100755)"


def test_direct_commit_on_main_is_refused(repo):
    _write_and_stage(repo, "a.txt", "a\n")
    result = git("commit", "-m", "direct on main", cwd=repo, check=False)
    assert result.returncode != 0, "the hook did not block a direct commit on main"
    assert "refusing a direct commit on `main`" in result.stderr
    assert "ALLOW_MAIN_COMMIT=1" in result.stderr
    # And nothing was committed.
    assert git("rev-list", "--count", "HEAD", cwd=repo).stdout.strip() == "1"


def test_the_override_allows_it(repo):
    _write_and_stage(repo, "a.txt", "a\n")
    result = git(
        "commit", "-m", "deliberate", cwd=repo, check=False, env={"ALLOW_MAIN_COMMIT": "1"}
    )
    assert result.returncode == 0, result.stderr
    assert "ALLOW_MAIN_COMMIT is set" in result.stderr
    assert git("rev-list", "--count", "HEAD", cwd=repo).stdout.strip() == "2"


def test_commits_on_any_other_branch_are_untouched(repo):
    git("checkout", "-q", "-b", "worktree-style-branch", cwd=repo)
    _write_and_stage(repo, "b.txt", "b\n")
    result = git("commit", "-m", "on a branch", cwd=repo, check=False)
    assert result.returncode == 0, result.stderr


def test_a_clean_merge_into_main_is_not_blocked(repo):
    """THE test. This project's history lands large verified fixes as a merge
    commit from a worktree branch into main (e.g. f385fc5). --no-ff forces a
    real merge commit rather than a fast-forward, which is the shape that
    would break if the hook were naive."""
    git("checkout", "-q", "-b", "feature", cwd=repo)
    _write_and_stage(repo, "feature.txt", "feature\n")
    git("commit", "-q", "-m", "feature work", cwd=repo)

    git("checkout", "-q", "main", cwd=repo)
    result = git("merge", "--no-ff", "-m", "Merge feature", "feature", cwd=repo, check=False)
    assert result.returncode == 0, f"the hook blocked a merge into main:\n{result.stderr}"

    log = git("log", "--oneline", "-1", cwd=repo).stdout
    assert "Merge feature" in log
    parents = git("rev-list", "--parents", "-n", "1", "HEAD", cwd=repo).stdout.split()
    assert len(parents) == 3, f"expected a two-parent merge commit, got {parents}"


def test_finishing_a_conflicted_merge_on_main_is_not_blocked(repo):
    """The case where the hook IS reached: a merge that stops for conflicts is
    finished by the user running `git commit`, which invokes pre-commit. git
    has written MERGE_HEAD by then, and that is what the hook keys on."""
    _write_and_stage(repo, "shared.txt", "from main\n")
    git("commit", "-q", "-m", "main side", cwd=repo, env={"ALLOW_MAIN_COMMIT": "1"})

    git("checkout", "-q", "-b", "conflicting", "HEAD~1", cwd=repo)
    _write_and_stage(repo, "shared.txt", "from the branch\n")
    git("commit", "-q", "-m", "branch side", cwd=repo)

    git("checkout", "-q", "main", cwd=repo)
    merge = git("merge", "conflicting", cwd=repo, check=False)
    assert merge.returncode != 0, "expected a conflict to set up this test"
    assert (repo / ".git" / "MERGE_HEAD").exists()

    (repo / "shared.txt").write_text("resolved\n")
    git("add", "shared.txt", cwd=repo)
    result = git("commit", "-m", "Merge conflicting, resolved", cwd=repo, check=False)
    assert result.returncode == 0, (
        f"the hook blocked the completion of a conflicted merge on main:\n{result.stderr}"
    )


def test_a_detached_head_is_not_treated_as_main(repo):
    _write_and_stage(repo, "a.txt", "a\n")
    git("commit", "-q", "-m", "one", cwd=repo, env={"ALLOW_MAIN_COMMIT": "1"})
    git("checkout", "-q", "--detach", cwd=repo)
    _write_and_stage(repo, "c.txt", "c\n")
    result = git("commit", "-m", "detached", cwd=repo, check=False)
    assert result.returncode == 0, result.stderr


def test_the_hook_works_from_a_linked_worktree(repo, tmp_path):
    """core.hooksPath is repository-level, so a linked worktree inherits it —
    which is how .claude/worktrees/* get the hook without a per-worktree
    install. The worktree is on its own branch, so committing there must be
    allowed; the point of the test is that the hook RUNS and does not crash on
    a worktree's non-standard git dir (where MERGE_HEAD lives under
    .git/worktrees/<name>/, which is why the hook uses `git rev-parse
    --git-path`)."""
    wt = tmp_path / "wt"
    git("worktree", "add", "-q", "-b", "wt-branch", str(wt), cwd=repo)
    shutil.copytree(repo / ".githooks", wt / ".githooks", dirs_exist_ok=True)
    _write_and_stage(wt, "d.txt", "d\n")
    result = git("commit", "-m", "in a worktree", cwd=wt, check=False)
    assert result.returncode == 0, result.stderr
    assert git("rev-parse", "--abbrev-ref", "HEAD", cwd=wt).stdout.strip() == "wt-branch"
