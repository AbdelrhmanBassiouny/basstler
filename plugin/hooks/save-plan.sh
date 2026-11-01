#!/bin/bash
set -euo pipefail

# Saves a plan's plan.yaml and roadmap.md to the personal-notes branch and
# regenerates the branch index in the same commit. Landed items are pruned, an
# emptied plan is removed, and a plan over basstler.plan.size_limits is refused.
#
# The save carries only what the session changed since it read the plan: each
# top-level field, item and the roadmap the session changed is applied onto the
# branch as it is now, and the save is refused when another writer changed the
# same part since. A push the branch rejects because it moved meanwhile is
# repeated from the fetch, up to --attempts times.
#
# Usage: save-plan.sh <plan-id> --manifest <plan.yaml> --roadmap <roadmap.md>
#                     [--read-at <commit>] [--attempts <count>]
#    or: save-plan.sh [<plan-id>]   (reads the PLAN-MANIFEST/PLAN-ROADMAP
#                                    markers in CLAUDE.local.md)
# --read-at: the personal-notes commit the session read the plan at; without
#            it, the branch as this save first fetches it.
# --attempts: how many pushes to make before giving up (default 5).
# Prints the plan's page on the plan site, which the push rebuilds.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/resolve-personal-notes-config.sh"

require_basstler_python

PLAN_ID=""
MANIFEST_SOURCE_FILE=""
ROADMAP_SOURCE_FILE=""
READ_AT=""
ATTEMPTS=5
while [ $# -gt 0 ]; do
  case "$1" in
    --read-at)
      READ_AT="$2"
      shift 2
      ;;
    --attempts)
      ATTEMPTS="$2"
      shift 2
      ;;
    --manifest)
      MANIFEST_SOURCE_FILE="$2"
      shift 2
      ;;
    --roadmap)
      ROADMAP_SOURCE_FILE="$2"
      shift 2
      ;;
    -*)
      echo "Unrecognized argument: $1" >&2
      exit 1
      ;;
    *)
      PLAN_ID="$1"
      shift
      ;;
  esac
done

if ! printf '%s' "${ATTEMPTS}" | grep -qE '^[1-9][0-9]*$'; then
  echo "--attempts must be a positive whole number, not '${ATTEMPTS}'." >&2
  exit 1
fi

if [ -n "${MANIFEST_SOURCE_FILE}" ] && [ -z "${ROADMAP_SOURCE_FILE}" ]; then
  echo "--manifest was given without --roadmap - they must be passed together." >&2
  exit 1
fi
if [ -z "${MANIFEST_SOURCE_FILE}" ] && [ -n "${ROADMAP_SOURCE_FILE}" ]; then
  echo "--roadmap was given without --manifest - they must be passed together." >&2
  exit 1
fi
BOOTSTRAP_FROM_FILES=0
if [ -n "${MANIFEST_SOURCE_FILE}" ]; then
  BOOTSTRAP_FROM_FILES=1
  if [ -z "${PLAN_ID}" ]; then
    echo "<plan-id> is required alongside --manifest/--roadmap - a brand-new" >&2
    echo "plan has no entry in the reverse index yet to auto-derive it from." >&2
    exit 1
  fi
fi

if [ "${BOOTSTRAP_FROM_FILES}" = "0" ]; then
  if [ ! -f "${CLAUDE_LOCAL_MD}" ]; then
    echo "No CLAUDE.local.md at the project root (${CLAUDE_LOCAL_MD}) - nothing to save." >&2
    exit 1
  fi
  if ! grep -q '^<!-- BEGIN-PLAN-MANIFEST:' "${CLAUDE_LOCAL_MD}" \
      || ! grep -q '^<!-- BEGIN-PLAN-ROADMAP:' "${CLAUDE_LOCAL_MD}"; then
    echo "CLAUDE.local.md has no plan-manifest/plan-roadmap section to extract." >&2
    echo "Run session-start.sh first (on a branch a plan already tracks), pass" >&2
    echo "--manifest/--roadmap file paths instead." >&2
    exit 1
  fi
fi

if ! fetch_personal_notes_branch; then
  echo "Branch '${NOTES_BRANCH}' doesn't exist yet (tried: ${ATTEMPTED_NOTES_REMOTES})." >&2
  echo "Run ./create-personal-notes-branch.sh first, then re-run this script." >&2
  exit 1
fi

if [ -z "${PLAN_ID}" ]; then
  PLAN_ID="$(plan_id_for_branch "$(git rev-parse --abbrev-ref HEAD)" || true)"
fi
if [ -z "${PLAN_ID}" ]; then
  echo "Could not determine which plan to save for - the current branch isn't in" >&2
  echo "the generated index yet. Pass the plan id explicitly:" >&2
  echo "  ${BASH_SOURCE[0]} <plan-id>" >&2
  exit 1
fi
if ! printf '%s' "${PLAN_ID}" | grep -qE '^[A-Za-z0-9][A-Za-z0-9_-]*$'; then
  echo "Invalid plan id '${PLAN_ID}' - must match ^[A-Za-z0-9][A-Za-z0-9_-]*\$" >&2
  echo "(no path separators, no '..', no leading dot/dash) - it is used directly" >&2
  echo "as a path component." >&2
  exit 1
fi

MANIFEST_FILE="$(mktemp)"
ROADMAP_FILE="$(mktemp)"
SCRATCH_DIR="$(mktemp -d)"
READ_PLAN_DIR="$(mktemp -d)"
SESSION_PLAN_DIR="$(mktemp -d)"
MERGED_PLAN_DIR="$(mktemp -d)"
SCRATCH_BRANCH="__save-plan-tmp-$$"
remove_scratch_worktree() {
  git worktree remove --force "${SCRATCH_DIR}" 2>/dev/null || rm -rf "${SCRATCH_DIR}"
  git branch -D "${SCRATCH_BRANCH}" > /dev/null 2>&1 || true
}
cleanup() {
  remove_scratch_worktree
  rm -rf "${READ_PLAN_DIR}" "${SESSION_PLAN_DIR}" "${MERGED_PLAN_DIR}"
  rm -f "${MANIFEST_FILE}" "${ROADMAP_FILE}"
}
trap cleanup EXIT

if [ "${BOOTSTRAP_FROM_FILES}" = "1" ]; then
  cp "${MANIFEST_SOURCE_FILE}" "${MANIFEST_FILE}"
  cp "${ROADMAP_SOURCE_FILE}" "${ROADMAP_FILE}"
else
  awk '/^<!-- BEGIN-PLAN-MANIFEST:/{flag=1; next} /^<!-- END-PLAN-MANIFEST -->$/{flag=0} flag' \
    "${CLAUDE_LOCAL_MD}" > "${MANIFEST_FILE}"
  awk '/^<!-- BEGIN-PLAN-ROADMAP:/{flag=1; next} /^<!-- END-PLAN-ROADMAP -->$/{flag=0} flag' \
    "${CLAUDE_LOCAL_MD}" > "${ROADMAP_FILE}"
fi

if [ ! -s "${MANIFEST_FILE}" ]; then
  echo "The plan manifest is empty - nothing to save." >&2
  exit 1
fi

MANIFEST_PLAN_ID="$("${BASSTLER_PYTHON}" -m "${PLAN_MANIFEST_TOOLS_MODULE}" read-id "${MANIFEST_FILE}")"
if [ "${MANIFEST_PLAN_ID}" != "${PLAN_ID}" ]; then
  echo "The plan manifest's 'id: ${MANIFEST_PLAN_ID}' does not match the plan" >&2
  echo "being saved ('${PLAN_ID}') - refusing to save under a mismatched key." >&2
  exit 1
fi

PLAN_DIRECTORY_PATH="$(plan_directory_path "${PLAN_ID}")"
MANIFEST_PATH="$(plan_manifest_path "${PLAN_ID}")"
ROADMAP_PATH="$(plan_roadmap_path "${PLAN_ID}")"

cp "${MANIFEST_FILE}" "${SESSION_PLAN_DIR}/${PLAN_MANIFEST_FILENAME}"
cp "${ROADMAP_FILE}" "${SESSION_PLAN_DIR}/${PLAN_ROADMAP_FILENAME}"

[ -n "${READ_AT}" ] || READ_AT="$(git rev-parse "${PERSONAL_NOTES_REFERENCE}")"
if ! git cat-file -e "${READ_AT}^{commit}" 2>/dev/null; then
  echo "--read-at '${READ_AT}' is not a commit of '${NOTES_BRANCH}' this clone has fetched." >&2
  exit 1
fi
for document_path in "${MANIFEST_PATH}" "${ROADMAP_PATH}"; do
  if git cat-file -e "${READ_AT}:${document_path}" 2>/dev/null; then
    git show "${READ_AT}:${document_path}" > "${READ_PLAN_DIR}/$(basename "${document_path}")"
  fi
done

ATTEMPT=1
while :; do
  remove_scratch_worktree
  git worktree add -b "${SCRATCH_BRANCH}" "${SCRATCH_DIR}" "${PERSONAL_NOTES_REFERENCE}" --quiet

  rm -rf "${MERGED_PLAN_DIR}"
  # Exits CHANGED_SINCE_READ when another writer changed a part this save changes.
  "${BASSTLER_PYTHON}" -m "${PLAN_MANIFEST_TOOLS_MODULE}" merge \
    --read "${READ_PLAN_DIR}" \
    --session "${SESSION_PLAN_DIR}" \
    --latest "${SCRATCH_DIR}/${PLAN_DIRECTORY_PATH}" \
    --output "${MERGED_PLAN_DIR}" || exit

  # Validated against the fetched notes branch, so a <plan-id>/<item-id> entry resolves.
  if ! "${BASSTLER_PYTHON}" -m "${PLAN_MANIFEST_TOOLS_MODULE}" validate \
    "${MERGED_PLAN_DIR}/${PLAN_MANIFEST_FILENAME}" \
    --plans-dir "${SCRATCH_DIR}/${PLANS_DIR}"; then
    echo "Nothing was saved - fix the manifest and save again." >&2
    exit 1
  fi

  # Prints "saved" or "removed"; exits 1 naming each broken limit.
  STAGED_PLAN="$("${BASSTLER_PYTHON}" -m "${PLAN_SIZE_LIMITS_MODULE}" stage \
    "${MERGED_PLAN_DIR}/${PLAN_MANIFEST_FILENAME}" \
    "${MERGED_PLAN_DIR}/${PLAN_ROADMAP_FILENAME}" \
    --manifest-destination "${SCRATCH_DIR}/${MANIFEST_PATH}" \
    --roadmap-destination "${SCRATCH_DIR}/${ROADMAP_PATH}")" || exit 1

  mkdir -p "$(dirname "${SCRATCH_DIR}/${PLAN_BRANCH_INDEX_PATH}")"
  "${BASSTLER_PYTHON}" -m "${PLAN_MANIFEST_TOOLS_MODULE}" regenerate-branch-index \
    --scratch-dir "${SCRATCH_DIR}" \
    --plans-dir "${PLANS_DIR}" \
    --manifest-filename "${PLAN_MANIFEST_FILENAME}" \
    --output "${SCRATCH_DIR}/${PLAN_BRANCH_INDEX_PATH}"

  git -C "${SCRATCH_DIR}" add --all -- \
    "${PLANS_DIR}" \
    "${PLAN_BRANCH_INDEX_PATH}"

  if git -C "${SCRATCH_DIR}" diff --cached --quiet; then
    echo "No changes to save - plan '${PLAN_ID}' on '${NOTES_BRANCH}' (remote '${ACTIVE_NOTES_REMOTE}') is already up to date."
    exit 0
  fi

  git -C "${SCRATCH_DIR}" commit --quiet -m "Update plan manifest for ${PLAN_ID}"
  if git -C "${SCRATCH_DIR}" push "${ACTIVE_NOTES_REMOTE}" "HEAD:${NOTES_BRANCH}"; then
    break
  fi
  if [ "${ATTEMPT}" -ge "${ATTEMPTS}" ]; then
    echo "Gave up after ${ATTEMPTS} rejected pushes to '${NOTES_BRANCH}' on '${ACTIVE_NOTES_REMOTE}' - nothing was saved." >&2
    exit 1
  fi
  ATTEMPT=$((ATTEMPT + 1))
  echo "'${NOTES_BRANCH}' moved during the save; merging onto it again (attempt ${ATTEMPT} of ${ATTEMPTS})." >&2
  if ! fetch_personal_notes_branch; then
    echo "Could not fetch '${NOTES_BRANCH}' again - nothing was saved." >&2
    exit 1
  fi
done

if [ "${STAGED_PLAN}" = "removed" ]; then
  echo "Every item of plan '${PLAN_ID}' has landed, so the plan was removed from '${NOTES_BRANCH}' on '${ACTIVE_NOTES_REMOTE}'."
  exit 0
fi
echo "Saved plan '${PLAN_ID}' (plan.yaml, roadmap.md, and the branch index) back to '${NOTES_BRANCH}' on '${ACTIVE_NOTES_REMOTE}'."
if PAGE_URL="$(plan_site_page_url "${PLAN_ID}")"; then
  echo "The push rebuilds its page on the plan site: ${PAGE_URL}"
else
  echo "No plan site lists this repository yet - /setup-personal-notes publishes one."
fi
