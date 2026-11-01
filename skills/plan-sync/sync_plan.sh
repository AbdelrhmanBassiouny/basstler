#!/bin/bash
set -euo pipefail

# Syncs one plan's manifest with GitHub: basstler.plan.sync_manifest_status marks every
# item whose pull request merged as done, and if that changed anything, the patched
# plan.yaml is pushed back to the personal-notes branch - which the plan site rebuilds
# from.
#
# Usage:
#   sync_plan.sh \
#     --plan-id <plan-id> \
#     --plan <plan.yaml path> \
#     --pr-data <pr_data.json path> \
#     [--plans-dir <directory holding every plan>]
#
# --plans-dir is forwarded to the sync: it validates the manifest, and a depends_on
# entry naming <plan-id>/<item-id> resolves against that directory.
#
# Prints basstler.plan.sync_manifest_status's {"corrected": [...]} summary to stdout.

# Locating resolve-personal-notes-config.sh is the one irreducible hardcoded path
# here: it defines every other shared path constant used below.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../hooks/resolve-personal-notes-config.sh"

PLAN_ID=""
PLAN_FILE=""
PULL_REQUEST_DATA_FILE=""
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
    --pr-data)
      PULL_REQUEST_DATA_FILE="$2"
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

if [ -z "${PLAN_ID}" ] || [ -z "${PLAN_FILE}" ] || [ -z "${PULL_REQUEST_DATA_FILE}" ]; then
  echo "Usage: ${BASH_SOURCE[0]} --plan-id <id> --plan <plan.yaml> --pr-data <pr_data.json> [--plans-dir <dir>]" >&2
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

CORRECTED_COUNT="$("${BASSTLER_PYTHON}" -m "${SYNC_SUMMARY_MODULE}" count-corrected "${SYNC_SUMMARY}")"

if [ "${CORRECTED_COUNT}" != "0" ]; then
  "${WRITE_PERSONAL_NOTES_FILE_SCRIPT}" \
    --source "${PLAN_FILE}" \
    --destination "$(plan_manifest_path "${PLAN_ID}")" \
    --message "Auto-sync ${PLAN_ID}: ${CORRECTED_COUNT} item(s) to done (merged on GitHub)"
fi

echo "${SYNC_SUMMARY}"
