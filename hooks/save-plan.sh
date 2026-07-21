#!/bin/bash
set -euo pipefail

# Persists edits made to CLAUDE.local.md's plan-manifest/plan-roadmap
# sections back onto the personal-notes branch, at
# .claude/personal/plans/<plan-id>/{plan.yaml,roadmap.md} - and regenerates
# the generated branch->plan-id reverse index
# (.claude/personal/plans/_generated/branch-index.yaml) in the same commit,
# scanning every plan's plan.yaml so it can never drift out of sync with
# the manifests it's derived from. See
# .claude/personal/plans/README.md (on the personal-notes branch) for the
# full plan.yaml schema, and .claude/skills/plan-dashboard/SKILL.md for how
# the manifest is consumed.
#
# This is the write half of the loop session-start.sh's own plan section
# points a session at when it wants to update a plan it's already tracking:
# edit CLAUDE.local.md between the BEGIN-PLAN-MANIFEST/END-PLAN-MANIFEST and
# BEGIN-PLAN-ROADMAP/END-PLAN-ROADMAP markers, then run this script.
#
# Usage (from anywhere, after editing CLAUDE.local.md):
#   "$CLAUDE_PROJECT_DIR/.claude/hooks/save-plan.sh" [<plan-id>]
#
# <plan-id> is optional if the current branch already appears in some
# plan's items[] (session-start.sh's plan_id_for_branch lookup resolves it,
# same as it did to populate CLAUDE.local.md in the first place) - pass it
# explicitly when creating a brand-new plan (not yet in the generated
# index, so there's nothing to auto-derive from), or when saving a plan
# from a branch that isn't itself one of its tracked items (e.g. a steward
# session coordinating the whole plan rather than working one item).
#
# Creating a brand-new plan: there is no separate create-plan.sh. Add the
# BEGIN-PLAN-MANIFEST/END-PLAN-MANIFEST and BEGIN-PLAN-ROADMAP/END-PLAN-ROADMAP
# marker pairs to CLAUDE.local.md yourself (session-start.sh only ever
# scaffolds them for a branch the index already resolves, which a brand-new
# plan by definition isn't in yet), write your plan.yaml/roadmap.md content
# between them, then run this script with the new plan's id explicitly.
#
# This script pushes data only. It never calls the Artifact tool (only a
# live Claude session can), so it does not regenerate the dashboard itself -
# it prints a reminder to run /plan-dashboard <plan-id> afterward.
#
# Requires python3 with PyYAML to parse/validate manifests and regenerate
# the reverse index (unlike session-start.sh's read path, which is
# grep/sed-only so it stays dependency-free on every session start - this
# script only runs when a session is actively editing a plan, where python3
# is a safe assumption in this repo).
#
# Resolves the remote/branch exactly like the other hook scripts (git
# config > environment variable > the zero-config default, plus the
# same-branch-upstream fallback - see fetch_personal_notes_branch in
# ./resolve-personal-notes-config.sh).
#
# Safe to re-run: a no-op if the extracted content already matches what's on
# the branch (checked across all three files it may touch). Does its work in
# a scratch worktree, so it never touches your current branch or working
# tree - and never touches the plan's own branch(es), or anything that could
# be merged: the manifest lives only on the personal-notes branch. Fails
# with a clear message if that branch doesn't exist yet on any resolved
# remote - run ./create-personal-notes-branch.sh first in that case.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/resolve-personal-notes-config.sh"

if ! command -v python3 > /dev/null 2>&1; then
  echo "python3 is required to parse/validate plan manifests and regenerate the branch index." >&2
  exit 1
fi
if ! python3 -c "import yaml" > /dev/null 2>&1; then
  echo "python3's PyYAML module is required (pip install pyyaml)." >&2
  exit 1
fi

if [ ! -f "${CLAUDE_LOCAL_MD}" ]; then
  echo "No CLAUDE.local.md at the project root (${CLAUDE_LOCAL_MD}) - nothing to save." >&2
  exit 1
fi

if ! grep -q '^<!-- BEGIN-PLAN-MANIFEST:' "${CLAUDE_LOCAL_MD}" \
    || ! grep -q '^<!-- BEGIN-PLAN-ROADMAP:' "${CLAUDE_LOCAL_MD}"; then
  echo "CLAUDE.local.md has no plan-manifest/plan-roadmap section to extract." >&2
  echo "Run session-start.sh first (on a branch a plan already tracks), or add" >&2
  echo "the marker pairs yourself when bootstrapping a brand-new plan - see the" >&2
  echo "header comment in this script." >&2
  exit 1
fi

if ! fetch_personal_notes_branch; then
  echo "Branch '${NOTES_BRANCH}' doesn't exist yet (tried: ${ATTEMPTED_NOTES_REMOTES})." >&2
  echo "Run ./create-personal-notes-branch.sh first, then re-run this script." >&2
  exit 1
fi

PLAN_ID="${1:-}"
if [ -z "${PLAN_ID}" ]; then
  PLAN_ID="$(plan_id_for_branch "$(git rev-parse --abbrev-ref HEAD)" || true)"
fi
if [ -z "${PLAN_ID}" ]; then
  echo "Could not determine which plan to save for - the current branch isn't in" >&2
  echo "the generated index yet. Pass the plan id explicitly:" >&2
  echo "  ${BASH_SOURCE[0]} <plan-id>" >&2
  exit 1
fi

MANIFEST_FILE="$(mktemp)"
ROADMAP_FILE="$(mktemp)"
SCRATCH_DIR="$(mktemp -d)"
cleanup() {
  git worktree remove --force "${SCRATCH_DIR}" 2>/dev/null || rm -rf "${SCRATCH_DIR}"
  git branch -D __save-plan-tmp > /dev/null 2>&1 || true
  rm -f "${MANIFEST_FILE}" "${ROADMAP_FILE}"
}
trap cleanup EXIT

awk '/^<!-- BEGIN-PLAN-MANIFEST:/{flag=1; next} /^<!-- END-PLAN-MANIFEST -->$/{flag=0} flag' \
  "${CLAUDE_LOCAL_MD}" > "${MANIFEST_FILE}"
awk '/^<!-- BEGIN-PLAN-ROADMAP:/{flag=1; next} /^<!-- END-PLAN-ROADMAP -->$/{flag=0} flag' \
  "${CLAUDE_LOCAL_MD}" > "${ROADMAP_FILE}"

if [ ! -s "${MANIFEST_FILE}" ]; then
  echo "The plan-manifest section is empty - nothing to save." >&2
  exit 1
fi

MANIFEST_PLAN_ID="$(python3 -c "
import sys, yaml
with open('${MANIFEST_FILE}') as f:
    plan = yaml.safe_load(f)
print(plan.get('id', ''))
")"
if [ "${MANIFEST_PLAN_ID}" != "${PLAN_ID}" ]; then
  echo "CLAUDE.local.md's plan-manifest 'id: ${MANIFEST_PLAN_ID}' does not match" >&2
  echo "the plan being saved ('${PLAN_ID}') - refusing to save under a mismatched key." >&2
  exit 1
fi

git branch -D __save-plan-tmp > /dev/null 2>&1 || true
git worktree add -b __save-plan-tmp "${SCRATCH_DIR}" FETCH_HEAD --quiet

PLAN_DIR="${SCRATCH_DIR}/.claude/personal/plans/${PLAN_ID}"
mkdir -p "${PLAN_DIR}"
cp "${MANIFEST_FILE}" "${PLAN_DIR}/plan.yaml"
cp "${ROADMAP_FILE}" "${PLAN_DIR}/roadmap.md"

INDEX_PATH=".claude/personal/plans/_generated/branch-index.yaml"
mkdir -p "$(dirname "${SCRATCH_DIR}/${INDEX_PATH}")"
python3 -c "
import glob, os, yaml

scratch = '${SCRATCH_DIR}'
lines = [
    '# Generated by save-plan.sh from every plans/*/plan.yaml - do not hand-edit.',
    '# Maps each item branch to the plan id that tracks it, so session-start.sh',
    '# can auto-load the parent plan for whatever branch is checked out.',
    'branches:',
]
seen = set()
for path in sorted(glob.glob(os.path.join(scratch, '.claude/personal/plans/*/plan.yaml'))):
    with open(path) as f:
        plan = yaml.safe_load(f)
    plan_id = plan['id']
    for item in plan.get('items', []):
        branch = item.get('branch')
        if not branch or branch in seen:
            continue
        seen.add(branch)
        lines.append(f'  {branch}: {plan_id}')

with open(os.path.join(scratch, '${INDEX_PATH}'), 'w') as f:
    f.write('\n'.join(lines) + '\n')
"

git -C "${SCRATCH_DIR}" add \
  ".claude/personal/plans/${PLAN_ID}/plan.yaml" \
  ".claude/personal/plans/${PLAN_ID}/roadmap.md" \
  "${INDEX_PATH}"

if git -C "${SCRATCH_DIR}" diff --cached --quiet; then
  echo "No changes to save - plan '${PLAN_ID}' on '${NOTES_BRANCH}' (remote '${ACTIVE_NOTES_REMOTE}') is already up to date."
  exit 0
fi

git -C "${SCRATCH_DIR}" commit --quiet -m "Update plan manifest for ${PLAN_ID}"
git -C "${SCRATCH_DIR}" push "${ACTIVE_NOTES_REMOTE}" "HEAD:${NOTES_BRANCH}"

echo "Saved plan '${PLAN_ID}' (plan.yaml, roadmap.md, and the branch index) back to '${NOTES_BRANCH}' on '${ACTIVE_NOTES_REMOTE}'."
echo "Run /plan-dashboard ${PLAN_ID} to refresh its dashboard Artifact - this script only pushes data, it can't call the Artifact tool itself."
