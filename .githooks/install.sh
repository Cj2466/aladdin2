#!/bin/sh
#
# One-time install of this repository's tracked git hooks.
#
#     ./.githooks/install.sh
#
# Sets core.hooksPath to .githooks. That is a repository-level setting, so it
# covers main AND every linked worktree under .claude/worktrees/ — worktrees
# share the repository config and do not each need their own install.
#
# REFUSES rather than assumes if .git/hooks/ already holds a real (non-sample)
# hook: core.hooksPath replaces .git/hooks/ wholesale, so installing over one
# would silently stop it running. See .githooks/README.md for the symlink
# alternative in that case.

set -eu

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

common_dir=$(git rev-parse --git-common-dir)
existing=$(find "$common_dir/hooks" -maxdepth 1 -type f ! -name '*.sample' 2>/dev/null || true)
if [ -n "$existing" ]; then
    printf '%s\n' "refusing to install: $common_dir/hooks already contains real hook(s):" >&2
    printf '%s\n' "$existing" >&2
    printf '%s\n' "core.hooksPath would stop them running. See .githooks/README.md." >&2
    exit 1
fi

chmod +x .githooks/pre-commit
git config core.hooksPath .githooks

printf '%s\n' "installed: core.hooksPath = $(git config --get core.hooksPath)"
printf '%s\n' "hooks now active:"
for hook in .githooks/*; do
    case "$hook" in
        *.md|*install.sh) continue ;;
    esac
    printf '  %s\n' "$(basename "$hook")"
done
printf '%s\n' "uninstall with: git config --unset core.hooksPath"
