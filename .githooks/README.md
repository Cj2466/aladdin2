# .githooks

Git hooks tracked in the repository. `.git/hooks/` is **not** tracked by git,
so a hook that lives only there is invisible to everyone else and is lost on a
fresh clone — hence this directory plus a one-time install step.

## Install (one command, once per clone)

```sh
./.githooks/install.sh
```

That sets `core.hooksPath` to `.githooks`, which applies to the repository and
**every linked worktree under `.claude/worktrees/`** — worktrees share the
repository config, so you do not repeat it per worktree.

Or set it by hand:

```sh
git config core.hooksPath .githooks
```

### Uninstall

```sh
git config --unset core.hooksPath
```

### If you would rather not use `core.hooksPath`

`core.hooksPath` replaces `.git/hooks/` wholesale — any hook still sitting in
`.git/hooks/` stops running once it is set. This repository had no active
hooks before 2026-09-05 (only git's stock `*.sample` files), so there is
nothing to lose here; the install script checks and refuses rather than
assuming. If you ever do need both, symlink instead:

```sh
ln -sf ../../.githooks/pre-commit .git/hooks/pre-commit
```

A symlink, not a copy, so an update to the tracked hook takes effect without
reinstalling.

## Hooks

### `pre-commit` — refuse a direct commit on `main`

This project's convention is one worktree per piece of work, merged into
`main` only after an independent verification pass. The convention was broken
under time pressure on 2026-08-31 and nothing enforced it.

* Blocks `git commit` while `HEAD` is `main`.
* **Does not block merge commits.** A clean `git merge` never invokes
  `pre-commit` at all (githooks(5): it "is invoked by git commit"), and a
  merge that stops for conflicts leaves `MERGE_HEAD`, which the hook checks
  for and allows. Landing verified work with `git merge --no-ff <branch>`
  needs nothing special.
* Does not block a detached `HEAD` (bisect, a checked-out tag, a rebase), which
  is not "on main".
* Explicit override for the rare legitimate case:

  ```sh
  ALLOW_MAIN_COMMIT=1 git commit ...
  ```

  An environment variable rather than a config setting on purpose: it has to
  be typed for that one commit and cannot be left on by accident.

`--no-verify` also bypasses it, as it bypasses every pre-commit hook. This is
a guard rail against the accidental case, not a permission system.
