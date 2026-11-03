#!/bin/bash
set -uo pipefail

# A minimal MCP server over stdio, one JSON-RPC message per line, with one tool that
# answers with report-environment.sh's lines as the server process sees them.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_NAME="basstler-plugin-probe"
TOOL_NAME="report_environment"
FALLBACK_PROTOCOL_VERSION="2025-06-18"
METHOD_NOT_FOUND=-32601

# Prints its argument as a JSON string, quotes included.
json_string() {
  local text="$1"
  text="${text//\\/\\\\}"
  text="${text//\"/\\\"}"
  text="${text//$'\t'/\\t}"
  text="${text//$'\n'/\\n}"
  printf '"%s"' "${text}"
}

respond() {
  printf '{"jsonrpc":"2.0","id":%s,"result":%s}\n' "$1" "$2"
}

while IFS= read -r message; do
  [[ "${message}" =~ \"method\"[[:space:]]*:[[:space:]]*\"([^\"]*)\" ]] || continue
  method="${BASH_REMATCH[1]}"
  [[ "${message}" =~ \"id\"[[:space:]]*:[[:space:]]*(\"[^\"]*\"|-?[0-9]+) ]] || continue
  id="${BASH_REMATCH[1]}"
  case "${method}" in
    initialize)
      version="${FALLBACK_PROTOCOL_VERSION}"
      if [[ "${message}" =~ \"protocolVersion\"[[:space:]]*:[[:space:]]*\"([^\"]*)\" ]]; then
        version="${BASH_REMATCH[1]}"
      fi
      respond "${id}" "{\"protocolVersion\":$(json_string "${version}"),\"capabilities\":{\"tools\":{}},\"serverInfo\":{\"name\":\"${SERVER_NAME}\",\"version\":\"0.0.1\"}}"
      ;;
    ping)
      respond "${id}" "{}"
      ;;
    tools/list)
      respond "${id}" "{\"tools\":[{\"name\":\"${TOOL_NAME}\",\"description\":\"Reports what this MCP server process received from Claude Code.\",\"inputSchema\":{\"type\":\"object\",\"properties\":{}}}]}"
      ;;
    tools/call)
      report="$(bash "${SCRIPT_DIR}/report-environment.sh" mcp-server)"
      respond "${id}" "{\"content\":[{\"type\":\"text\",\"text\":$(json_string "${report}")}],\"isError\":false}"
      ;;
    *)
      printf '{"jsonrpc":"2.0","id":%s,"error":{"code":%s,"message":%s}}\n' \
        "${id}" "${METHOD_NOT_FOUND}" "$(json_string "method not found: ${method}")"
      ;;
  esac
done
