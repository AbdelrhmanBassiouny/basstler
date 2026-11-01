#!/bin/bash
set -euo pipefail

# Orchestrates one plan's refresh: basstler.plan.sync_manifest_status's auto-correction,
# pushing that correction back to the personal-notes branch if it changed
# anything, then basstler.dashboard.plan_page's render - the exact sequence
# skills/plan-dashboard/SKILL.md step 2 previously spelled out as an
# embedded bash snippet for a session to improvise from. Extracted so that
# sequence is real, tested-by-construction code (it just calls the two
# modules test/basstler_test/ already covers) rather than
# prose a session re-derives - and re-risks getting subtly wrong - on every
# run.
#
# Usage:
#   refresh_dashboard.sh \
#     --plan-id <plan-id> \
#     --plan <plan.yaml path> \
#     --roadmap <roadmap.md path> \
#     --pr-data <pr_data.json path> \
#     --artifact-directory <directory to write the dashboard Artifact's files to> \
#     [--tracking-url <url>] [--hub-url <url>] [--index-url <url>] \
#     [--plans-dir <directory holding every plan>]
#
# --plans-dir is forwarded to both scripts below: each validates the manifest,
# and a depends_on entry naming <plan-id>/<item-id> resolves against that
# directory.
#
# Prints one JSON summary to stdout, merging basstler.plan.sync_manifest_status's own
# {"corrected": [...]} with basstler.dashboard.plan_page's status/drift/ready summary,
# so the calling skill has everything it needs from one place.
#
# Requires PyYAML, Jinja2, and the markdown package - see the package's own
# pyproject.toml, which declares them next to the modules that need them.

# Locating resolve-personal-notes-config.sh is the one irreducible hardcoded
# path here: it's the file that defines every other shared path constant
# used below (BUILD_DASHBOARD_MODULE, WRITE_PERSONAL_NOTES_FILE_SCRIPT, ...),
# so it can't itself be referenced through one of them. Sourcing it also
# `cd`s to the project root, so every one of its path constants below can be
# used exactly as written - no further path arithmetic needed.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../hooks/resolve-personal-notes-config.sh"

PLAN_ID=""
PLAN_FILE=""
ROADMAP_FILE=""
PULL_REQUEST_DATA_FILE=""
ARTIFACT_DIRECTORY=""
TRACKING_URL=""
HUB_URL=""
INDEX_URL=""
PLANS_DIRECTORY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --plan-id)
      PLAN_ID="$2"
      shift 2
      ;;
    --plan)
      PLAN_FILE="$2"
      shift 2
      ;;
    --roadmap)
      ROADMAP_FILE="$2"
      shift 2
      ;;
    --pr-data)
      PULL_REQUEST_DATA_FILE="$2"
      shift 2
      ;;
    --artifact-directory)
      ARTIFACT_DIRECTORY="$2"
      shift 2
      ;;
    --tracking-url)
      TRACKING_URL="$2"
      shift 2
      ;;
    --hub-url)
      HUB_URL="$2"
      shift 2
      ;;
    --index-url)
      INDEX_URL="$2"
      shift 2
      ;;
    --plans-dir)
      PLANS_DIRECTORY="$2"
      shift 2
      ;;
    *)
      echo "Unrecognized argument: $1" >&2
      exit 1
      ;;
  esac
done

if [ -z "${PLAN_ID}" ] || [ -z "${PLAN_FILE}" ] || [ -z "${ROADMAP_FILE}" ] \
    || [ -z "${PULL_REQUEST_DATA_FILE}" ] || [ -z "${ARTIFACT_DIRECTORY}" ]; then
  echo "Usage: ${BASH_SOURCE[0]} --plan-id <id> --plan <plan.yaml> --roadmap <roadmap.md> --pr-data <pr_data.json> --artifact-directory <dir> [--tracking-url <url>] [--hub-url <url>] [--index-url <url>] [--plans-dir <dir>]" >&2
  exit 1
fi

PLANS_DIRECTORY_ARGUMENTS=()
if [ -n "${PLANS_DIRECTORY}" ]; then
  PLANS_DIRECTORY_ARGUMENTS=(--plans-dir "${PLANS_DIRECTORY}")
fi

SYNC_SUMMARY="$("${BASSTLER_PYTHON}" -m "${SYNC_MANIFEST_STATUS_MODULE}" \
  --plan "${PLAN_FILE}" \
  --pr-data "${PULL_REQUEST_DATA_FILE}" \
  "${PLANS_DIRECTORY_ARGUMENTS[@]+"${PLANS_DIRECTORY_ARGUMENTS[@]}"}")"

CORRECTED_COUNT="$("${BASSTLER_PYTHON}" -m "${REFRESH_DASHBOARD_SUPPORT_MODULE}" count-corrected "${SYNC_SUMMARY}")"

if [ "${CORRECTED_COUNT}" != "0" ]; then
  DESTINATION_PATH="$(plan_manifest_path "${PLAN_ID}")"
  "${WRITE_PERSONAL_NOTES_FILE_SCRIPT}" \
    --source "${PLAN_FILE}" \
    --destination "${DESTINATION_PATH}" \
    --message "Auto-sync ${PLAN_ID}: ${CORRECTED_COUNT} item(s) to done (merged on GitHub)"
fi

BUILD_ARGUMENTS=(
  --plan "${PLAN_FILE}"
  --roadmap "${ROADMAP_FILE}"
  --pr-data "${PULL_REQUEST_DATA_FILE}"
  --artifact-directory "${ARTIFACT_DIRECTORY}"
)
if [ -n "${TRACKING_URL}" ]; then
  BUILD_ARGUMENTS+=(--tracking-url "${TRACKING_URL}")
fi
if [ -n "${HUB_URL}" ]; then
  BUILD_ARGUMENTS+=(--hub-url "${HUB_URL}")
fi
if [ -n "${INDEX_URL}" ]; then
  BUILD_ARGUMENTS+=(--index-url "${INDEX_URL}")
fi
if [ -n "${PLANS_DIRECTORY}" ]; then
  BUILD_ARGUMENTS+=(--plans-dir "${PLANS_DIRECTORY}")
fi
mkdir -p "${ARTIFACT_DIRECTORY}"
BUILD_SUMMARY="$("${BASSTLER_PYTHON}" -m "${BUILD_DASHBOARD_MODULE}" "${BUILD_ARGUMENTS[@]}")"

"${BASSTLER_PYTHON}" -m "${REFRESH_DASHBOARD_SUPPORT_MODULE}" merge-summaries \
  "${SYNC_SUMMARY}" "${BUILD_SUMMARY}"
