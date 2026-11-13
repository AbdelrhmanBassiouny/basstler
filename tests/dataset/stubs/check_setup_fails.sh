#!/bin/bash
set -uo pipefail

# Test stub standing in for check-setup.sh when it fails before printing a
# report, so the setup's handling of that failure can be tested.
#   STUB_CHECK_SETUP_ERROR  - what it prints to standard error
#   STUB_CHECK_SETUP_STATUS - the status it exits with

printf '%s\n' "${STUB_CHECK_SETUP_ERROR}" >&2
exit "${STUB_CHECK_SETUP_STATUS}"
