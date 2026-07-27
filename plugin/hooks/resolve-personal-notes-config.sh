# Sourced (not executed) by session-start.sh, create-personal-notes-branch.sh,
# save-personal-notes.sh and save-pr-progress.sh, so all four resolve the
# personal-notes remote, branch and path with the exact same precedence: git
# config > environment variable > the zero-config default. See ./README.md.

# CLAUDE_LOCAL_MD: the one, deterministic path to CLAUDE.local.md, always the
# project root regardless of the caller's current working directory. Derived
# from this file's own location on disk (${BASH_SOURCE[0]}, which - inside a
# sourced file - is that file's own path, not the sourcing script's) rather
# than $CLAUDE_PROJECT_DIR or the caller's cwd: a SessionStart hook's cwd
# isn't guaranteed to be the project root (see session-start.sh), and these
# scripts are also run directly, outside any hook, where nothing guarantees
# $CLAUDE_PROJECT_DIR is set at all. This file always lives at
# <project-root>/.claude/hooks/resolve-personal-notes-config.sh, so two
# levels up from its own directory is always the project root, unconditionally.
HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HOOKS_DIR}/../.." && pwd)"
CLAUDE_LOCAL_MD="${PROJECT_ROOT}/CLAUDE.local.md"

# Every caller also does `git` operations (config, fetch, worktree, branch)
# that assume they're running inside this repo. Move there explicitly instead
# of trusting the invoking cwd to already be inside it (or inside it at all) -
# git itself would otherwise auto-discover a *different* repo if run from
# inside some other one, or fail outright if run from outside any repo.
cd "${PROJECT_ROOT}"

NOTES_REMOTE="$(git config --get claude.personalNotesRemote || true)"
NOTES_REMOTE="${NOTES_REMOTE:-${CLAUDE_PERSONAL_NOTES_REMOTE:-origin}}"

NOTES_BRANCH="$(git config --get claude.personalNotesBranch || true)"
NOTES_BRANCH="${NOTES_BRANCH:-${CLAUDE_PERSONAL_NOTES_BRANCH:-claude/personal-notes}}"

NOTES_PATH="$(git config --get claude.personalNotesPath || true)"
NOTES_PATH="${NOTES_PATH:-${CLAUDE_PERSONAL_NOTES_PATH:-.claude/personal/cram-notes.md}}"

# NOTES_REMOTE may be either a configured remote's name (e.g. "origin") or a
# raw git URL (e.g. "https://github.com/<you>/<repo>") - `git fetch`/`git
# push` accept both interchangeably, and a URL needs no `git remote add`
# first. Use a URL whenever your own fork isn't the clone's "origin" (for
# example, some session environments name the upstream repo "origin" and your
# fork something else) - the URL form works without depending on that
# session-specific remote name/alias existing at all.

# current_branch_upstream_remote: prints the remote name the current branch
# tracks (e.g. "abdel-direct" for a branch whose upstream is
# "abdel-direct/some-branch"), or nothing if it has no upstream (detached
# HEAD, or a branch that was never pushed with -u/--set-upstream). Shared by
# fetch_personal_notes_branch below and by create-personal-notes-branch.sh's
# existence check, so both apply the exact same fallback remote.
current_branch_upstream_remote() {
  git rev-parse --abbrev-ref --symbolic-full-name @{upstream} 2>/dev/null | cut -d/ -f1
}

# fetch_personal_notes_branch: fetches NOTES_BRANCH from NOTES_REMOTE. If that
# fails (remote unreachable, or the branch just isn't there), falls back once
# to the current branch's own upstream remote (current_branch_upstream_remote
# above) - if it has one, and it differs from NOTES_REMOTE - before giving up.
# This covers the common case of a clone whose checked-out branch already
# tracks a contributor's own fork under some other remote name/URL, without
# requiring NOTES_REMOTE to be configured explicitly for it.
#
# On success: sets ACTIVE_NOTES_REMOTE to whichever remote actually served
# the branch (NOTES_REMOTE or the upstream fallback), leaves the fetched
# commit in FETCH_HEAD (see the note on FETCH_HEAD vs. "<remote>/<branch>"
# refs in session-start.sh), and returns 0.
# On failure: sets ATTEMPTED_NOTES_REMOTES to a human-readable, comma
# separated list of every remote that was tried (for callers that want to
# report it), and returns 1.
#
# Read-only fallback: this never affects where create-personal-notes-branch.sh
# creates the branch, or (by itself) where save-personal-notes.sh pushes an
# edit back to - callers that push should push back to ACTIVE_NOTES_REMOTE,
# i.e. wherever the branch was actually read from, not unconditionally to
# NOTES_REMOTE, so a save always lands on the same remote the notes came from.
fetch_personal_notes_branch() {
  ATTEMPTED_NOTES_REMOTES="${NOTES_REMOTE}"
  if git fetch "${NOTES_REMOTE}" "${NOTES_BRANCH}" --quiet 2>/dev/null; then
    ACTIVE_NOTES_REMOTE="${NOTES_REMOTE}"
    return 0
  fi

  local upstream_remote
  upstream_remote="$(current_branch_upstream_remote)"
  if [ -n "${upstream_remote}" ] && [ "${upstream_remote}" != "${NOTES_REMOTE}" ]; then
    ATTEMPTED_NOTES_REMOTES="${ATTEMPTED_NOTES_REMOTES}, ${upstream_remote}"
    if git fetch "${upstream_remote}" "${NOTES_BRANCH}" --quiet 2>/dev/null; then
      ACTIVE_NOTES_REMOTE="${upstream_remote}"
      return 0
    fi
  fi

  return 1
}

# pr_progress_path: prints the deterministic per-branch PR-progress file path
# (.claude/personal/pr-progress/<branch>.md) for whichever branch is currently
# checked out, and returns 0. Returns 1 (prints nothing) if there's no
# sensible "current PR" to track progress for: detached HEAD, the repo's
# default branch (main/master), or the personal-notes branch itself. The
# directory is a fixed convention, independent of NOTES_PATH - PR progress is
# inherently plural/keyed, unlike the single personal-notes file, so it isn't
# tied to wherever NOTES_PATH happens to be overridden to.
#
# Shared by session-start.sh and save-pr-progress.sh so both agree on exactly
# the same key for exactly the same branch - there is no other place this
# path is computed, so it can never drift between reading and writing it.
pr_progress_path() {
  local branch
  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
  case "${branch}" in
    HEAD|main|master|"${NOTES_BRANCH}"|"") return 1 ;;
  esac
  printf '.claude/personal/pr-progress/%s.md\n' "${branch}"
}

# PLANS_DIR / PLAN_MANIFEST_FILENAME / PLAN_ROADMAP_FILENAME: the one,
# shared definition of where a plan's files live, so no caller re-derives
# these path fragments itself (session-start.sh and save-plan.sh both used
# to build ".claude/personal/plans/<id>/plan.yaml" inline - two independent
# copies of the same literal that could silently drift apart). Fixed
# convention, never overridden - plan storage is plural/generated data, not
# a per-clone preference like NOTES_PATH.
PLANS_DIR=".claude/personal/plans"
PLAN_MANIFEST_FILENAME="plan.yaml"
PLAN_ROADMAP_FILENAME="roadmap.md"

# plan_directory_path / plan_manifest_path / plan_roadmap_path: the
# deterministic per-plan paths for the given plan id. Shared by
# session-start.sh and save-plan.sh so both agree on exactly the same
# layout - see pr_progress_path above for the same reasoning applied to
# PR-progress files.
plan_directory_path() {
  printf '%s/%s\n' "${PLANS_DIR}" "$1"
}
plan_manifest_path() {
  printf '%s/%s/%s\n' "${PLANS_DIR}" "$1" "${PLAN_MANIFEST_FILENAME}"
}
plan_roadmap_path() {
  printf '%s/%s/%s\n' "${PLANS_DIR}" "$1" "${PLAN_ROADMAP_FILENAME}"
}

# PLAN_BRANCH_INDEX_PATH: the generated reverse index mapping every plan
# item's branch to the plan id that tracks it (see
# .claude/personal/plans/README.md on the personal-notes branch for the
# full plan-dashboard schema this feeds).
PLAN_BRANCH_INDEX_PATH="${PLANS_DIR}/_generated/branch-index.tsv"

# PLAN_DASHBOARD_DIR / *_SCRIPT / *_FILE: the canonical location of every
# script, hook, and requirements file the plan-dashboard/plan-item-*/CI
# tooling invokes - defined once, here, so refresh_dashboard.sh, every
# plan-*/SKILL.md, and .github/workflows/ci.yml source this file and use
# these variables instead of each carrying its own separately-typed literal
# path (exactly the drift risk a reviewer flagged after those paths had
# already been duplicated across all of them). Relative to the project
# root, which sourcing this file already `cd`s into (see PROJECT_ROOT
# above) - so every caller can use these directly, with no further path
# arithmetic of its own.
PLAN_DASHBOARD_DIR=".claude/skills/plan-dashboard"
BUILD_DASHBOARD_SCRIPT="${PLAN_DASHBOARD_DIR}/build_dashboard.py"
BUILD_INDEX_SCRIPT="${PLAN_DASHBOARD_DIR}/build_index.py"
SYNC_MANIFEST_STATUS_SCRIPT="${PLAN_DASHBOARD_DIR}/sync_manifest_status.py"
CHECK_DEPENDENCY_READINESS_SCRIPT="${PLAN_DASHBOARD_DIR}/check_dependency_readiness.py"
REFRESH_DASHBOARD_SCRIPT="${PLAN_DASHBOARD_DIR}/refresh_dashboard.sh"
REFRESH_DASHBOARD_SUPPORT_SCRIPT="${PLAN_DASHBOARD_DIR}/refresh_dashboard_support.py"
PLAN_DASHBOARD_REQUIREMENTS_FILE="${PLAN_DASHBOARD_DIR}/requirements.txt"
PLAN_DASHBOARD_TESTS_DIR="${PLAN_DASHBOARD_DIR}/tests"
WRITE_PERSONAL_NOTES_FILE_SCRIPT=".claude/hooks/write-personal-notes-file.sh"

# plan_id_for_branch: prints the plan id that tracks the given branch, per
# PLAN_BRANCH_INDEX_PATH on FETCH_HEAD, and returns 0. Returns 1 (prints
# nothing) if the index doesn't exist yet, or the branch isn't in it. Caller
# must have already fetched NOTES_BRANCH successfully (see
# fetch_personal_notes_branch) - this reads FETCH_HEAD directly rather than
# fetching again itself, so session-start.sh and save-plan.sh each fetch
# exactly once per run.
#
# The index is tab-separated values (TSV): one "<branch><TAB><plan-id>" line
# per branch, generated fresh in full by ./save-plan.sh on every run (never
# hand-edited or incrementally patched). TSV rather than a hand-rolled
# YAML-lookalike matched by fixed-string grep: it's an unambiguous, widely
# understood interchange format - a tab can never appear inside a branch
# name or plan id, so a field-based match can't misfire the way a
# substring/prefix match on a YAML-shaped string could - while still
# needing nothing beyond `awk`, which every session-start environment
# already has (see the module docstring: session-start.sh must not gain a
# hard dependency on python3/PyYAML just to check whether the current
# branch belongs to a plan).
plan_id_for_branch() {
  local branch="$1"
  git cat-file -e "FETCH_HEAD:${PLAN_BRANCH_INDEX_PATH}" 2>/dev/null || return 1
  git show "FETCH_HEAD:${PLAN_BRANCH_INDEX_PATH}" 2>/dev/null \
    | awk -F'\t' -v branch="${branch}" '$1 == branch { print $2; exit }'
}
