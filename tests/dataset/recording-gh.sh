#!/usr/bin/env bash
# Stands in for gh: records each call's arguments, the GH_TOKEN it ran with and its
# standard input, and fails a workflow run when GH_WORKFLOW_RUN_STATUS says so.
if [ "$1" = "workflow" ]; then
  printf '%s|%s|\n' "${GH_TOKEN-}" "$*" >> "$GH_CALLS"
  exit "${GH_WORKFLOW_RUN_STATUS:-0}"
fi
printf '%s|%s|%s\n' "${GH_TOKEN-}" "$*" "$(cat)" >> "$GH_CALLS"
