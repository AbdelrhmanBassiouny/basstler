#!/bin/bash
set -uo pipefail

# Test stub standing in for the bash Claude Code is configured with
# (CLAUDE_CODE_GIT_BASH_PATH), so a test can tell which bash a script was run
# in. Copied into place as an executable named `bash`; never on PATH, so the
# real bash it hands over to is the one PATH finds.
#   STUB_BASH_CALL_LOG - file each run's first argument, the script, is
#                        appended to

printf '%s\n' "${1:-}" >> "${STUB_BASH_CALL_LOG}"
exec bash "$@"
