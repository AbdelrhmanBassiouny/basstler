#!/bin/bash
set -uo pipefail

# Prints, one `name=value` line each, what a plugin process received from Claude Code:
#   report-environment.sh <reporter>
# <reporter> names the process asking (the MCP server, the SessionStart hook), so the
# lines say where they came from. An unset variable prints as `<unset>`.

REPORTER="${1:?usage: report-environment.sh <reporter>}"

report() {
  printf '%s %s=%s\n' "${REPORTER}" "$1" "$2"
}

report CLAUDE_PLUGIN_ROOT "${CLAUDE_PLUGIN_ROOT:-<unset>}"
report CLAUDE_PLUGIN_DATA "${CLAUDE_PLUGIN_DATA:-<unset>}"
report CLAUDE_PLUGIN_OPTION_PROBE_VALUE "${CLAUDE_PLUGIN_OPTION_PROBE_VALUE:-<unset>}"
report PROBE_OPTION "${PROBE_OPTION:-<unset>}"
report CLAUDE_CODE_REMOTE "${CLAUDE_CODE_REMOTE:-<unset>}"

if [ -n "${CLAUDE_PLUGIN_DATA:-}" ] && mkdir -p "${CLAUDE_PLUGIN_DATA}" && touch "${CLAUDE_PLUGIN_DATA}/written-by-probe"; then
  report plugin_data_writable yes
else
  report plugin_data_writable no
fi
report uv "$(command -v uv || echo '<not found>')"
report python3 "$(command -v python3 || echo '<not found>')"
