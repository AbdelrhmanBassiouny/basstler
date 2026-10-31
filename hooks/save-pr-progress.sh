#!/bin/bash
set -euo pipefail

# Persists edits made to CLAUDE.local.md's PR-progress section back onto the
# personal-notes branch, at a path keyed to the branch currently checked out
# (see pr_progress_path in ./resolve-personal-notes-config.sh) - so the
# plan/progress/next-steps for *this* PR survives session restarts, without
# ever being committed to the PR branch itself. This is the write half of the
# loop session-start.sh's own PR-progress header points Claude at when asked
# to update the plan: edit CLAUDE.local.md between the BEGIN-PR-PROGRESS /
# END-PR-PROGRESS markers, then run this script.
#
# Usage (from anywhere, after editing CLAUDE.local.md):
#   "${BASSTLER_PLUGIN_ROOT}/hooks/save-pr-progress.sh" [--branch <branch>] [--source <file>]
#
# --branch saves the progress of <branch> rather than of the branch checked out
# in the project root - for a session working a branch in a worktree of its
# own. --source takes the progress from <file> rather than from CLAUDE.local.md,
# whose section holds the checked-out branch's progress.
#
# Always reads the project root's CLAUDE.local.md specifically (see
# CLAUDE_LOCAL_MD in ./resolve-personal-notes-config.sh), regardless of the
# invoking cwd - not whatever CLAUDE.local.md a bare relative path might
# happen to resolve to from wherever this is run.
#
# Resolves the remote/branch exactly like session-start.sh and
# save-personal-notes.sh (git config > environment variable > the zero-config
# default, plus the same-branch-upstream fallback - see
# fetch_personal_notes_branch in ./resolve-personal-notes-config.sh). The path
# is never configured directly - it's always derived from the branch named
# with --branch, else the one checked out, by the same pr_progress_path
# session-start.sh reads it through.
#
# Refuses to run on a branch with no sensible "current PR" (the default
# branch, a detached HEAD, or the personal-notes branch itself), or if
# CLAUDE.local.md has no PR-progress section to extract - run
# session-start.sh first in that case.
#
# Safe to re-run: a no-op if the extracted content already matches what's on
# the branch. Does its work in a scratch worktree, so it never touches your
# current branch or working tree - and never touches the PR branch itself, or
# anything that could be merged: the progress file lives only on the
# personal-notes branch. Fails with a clear message if that branch doesn't
# exist yet on any resolved remote - run ./create-personal-notes-branch.sh
# first in that case.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/resolve-personal-notes-config.sh"

BRANCH=""
SOURCE_FILE=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --branch) BRANCH="${2:?--branch needs a branch}"; shift 2 ;;
    --source) SOURCE_FILE="${2:?--source needs a file}"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

require_basstler_python

PROGRESS_PATH="$(pr_progress_path "${BRANCH}" || true)"
if [ -z "${PROGRESS_PATH}" ]; then
  echo "Not a PR branch (the default branch, a detached HEAD, or the personal-notes branch itself) - nothing to save." >&2
  echo "Name the branch whose progress you want to save with --branch, then re-run this script." >&2
  exit 1
fi
[ -n "${BRANCH}" ] || BRANCH="$(git rev-parse --abbrev-ref HEAD)"

if [ -n "${SOURCE_FILE}" ] && [ ! -f "${SOURCE_FILE}" ]; then
  echo "No progress file at ${SOURCE_FILE} - nothing to save." >&2
  exit 1
fi

if [ -z "${SOURCE_FILE}" ] && [ ! -f "${CLAUDE_LOCAL_MD}" ]; then
  echo "No CLAUDE.local.md at the project root (${CLAUDE_LOCAL_MD}) - nothing to save." >&2
  exit 1
fi

if [ -z "${SOURCE_FILE}" ] && ! grep -q '^<!-- BEGIN-PR-PROGRESS -->$' "${CLAUDE_LOCAL_MD}"; then
  echo "CLAUDE.local.md has no PR-progress section to extract." >&2
  echo "Run session-start.sh first, then edit the section it writes." >&2
  exit 1
fi

if ! fetch_personal_notes_branch; then
  echo "Branch '${NOTES_BRANCH}' doesn't exist yet (tried: ${ATTEMPTED_NOTES_REMOTES})." >&2
  echo "Run ./create-personal-notes-branch.sh first, then re-run this script." >&2
  exit 1
fi

CONTENT_FILE="$(mktemp)"
SCRATCH_DIR="$(mktemp -d)"
cleanup() {
  git worktree remove --force "${SCRATCH_DIR}" 2>/dev/null || rm -rf "${SCRATCH_DIR}"
  git branch -D __save-pr-progress-tmp > /dev/null 2>&1 || true
  rm -f "${CONTENT_FILE}"
}
trap cleanup EXIT

if [ -n "${SOURCE_FILE}" ]; then
  cp "${SOURCE_FILE}" "${CONTENT_FILE}"
else
  awk '/^<!-- BEGIN-PR-PROGRESS -->$/{flag=1; next} /^<!-- END-PR-PROGRESS -->$/{flag=0} flag' \
    "${CLAUDE_LOCAL_MD}" > "${CONTENT_FILE}"
fi

"${BASSTLER_PYTHON}" -m "${PLAN_SIZE_LIMITS_MODULE}" check-progress "${CONTENT_FILE}" || exit 1

git branch -D __save-pr-progress-tmp > /dev/null 2>&1 || true
# FETCH_HEAD: see the note on FETCH_HEAD vs. "<remote>/<branch>" refs in
# save-personal-notes.sh - a URL-form remote has no tracking ref, and
# FETCH_HEAD is shared across worktrees so this scratch worktree sees the
# fetch above correctly regardless.
git worktree add -b __save-pr-progress-tmp "${SCRATCH_DIR}" FETCH_HEAD --quiet

mkdir -p "${SCRATCH_DIR}/$(dirname "${PROGRESS_PATH}")"
cp "${CONTENT_FILE}" "${SCRATCH_DIR}/${PROGRESS_PATH}"

# Progress notes no session will read again - a branch gone from the remote,
# or one whose pull requests have all merged or closed - are deleted in the
# same commit. Never fatal: the save goes ahead unpruned if this fails.
"${BASSTLER_PYTHON}" -m "${PROGRESS_NOTES_MODULE}" prune \
  --directory "${SCRATCH_DIR}/${PR_PROGRESS_DIRECTORY}" \
  --remote "$(git config "branch.${BRANCH}.remote" || echo origin)" \
  --keep "${BRANCH}" \
  || echo "Pruning finished branches' progress notes failed (above); saving without it." >&2
git -C "${SCRATCH_DIR}" add --all -- "${PR_PROGRESS_DIRECTORY}"

if git -C "${SCRATCH_DIR}" diff --cached --quiet -- "${PR_PROGRESS_DIRECTORY}"; then
  echo "No changes to save - '${PROGRESS_PATH}' on '${NOTES_BRANCH}' (remote '${ACTIVE_NOTES_REMOTE}') is already up to date."
  exit 0
fi

git -C "${SCRATCH_DIR}" commit --quiet -m "Update PR progress for ${BRANCH}"
git -C "${SCRATCH_DIR}" push "${ACTIVE_NOTES_REMOTE}" "HEAD:${NOTES_BRANCH}"

echo "Saved '${PROGRESS_PATH}' back to '${NOTES_BRANCH}' on '${ACTIVE_NOTES_REMOTE}'."
