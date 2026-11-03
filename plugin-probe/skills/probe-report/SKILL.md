---
name: probe-report
description: Report whether this probe plugin's MCP server, userConfig option, data directory and SessionStart hook reached this session. Invoke as "/basstler-plugin-probe:probe-report". Use only when asked to run the plugin probe.
---

# Plugin probe report

Gather each row below, then print the table, ready to paste into a pull request.
Report what you see; never guess a row.

1. **MCP server.** Is a tool whose name ends in `report_environment` among your tools,
   or does `ToolSearch` find one? If so, call it and copy its lines. If not, say which.
2. **Skill substitution.** Claude Code substitutes these three values into this file as
   it loads it. Copy them as you see them here:
   - `user_config.probe_value`: `${user_config.probe_value}`
   - `CLAUDE_PLUGIN_DATA`: `${CLAUDE_PLUGIN_DATA}`
   - `CLAUDE_PLUGIN_ROOT`: `${CLAUDE_PLUGIN_ROOT}`
3. **SessionStart hook.** Copy the lines starting with `session-start-hook` from this
   session's start context, or say that none are there.
4. **Bash tool.** Run `env | grep -E '^(CLAUDE_PLUGIN|PROBE_OPTION)' || echo none` and copy
   what it prints.
5. **Where the plugin landed.** Run `ls -a "${CLAUDE_PLUGIN_ROOT}"` and copy what it prints.

| Check | Seen |
| --- | --- |
| MCP tool listed | |
| MCP server: `PROBE_OPTION`, `CLAUDE_PLUGIN_DATA`, data writable, `uv` | |
| Skill: `user_config.probe_value`, `CLAUDE_PLUGIN_DATA` | |
| Hook: `CLAUDE_PLUGIN_OPTION_PROBE_VALUE`, `CLAUDE_PLUGIN_DATA` | |
| Bash tool environment | |
| Plugin root contents | |
