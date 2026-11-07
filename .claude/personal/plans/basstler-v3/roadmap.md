# basstler-v3 — standing rules

- Code does the mechanics and Claude only judges: a skill runs one command that prints a brief of at most 3 KB, decides, and records with one command.
- GitHub is the only store of state; nothing caches plans, stacks, URLs or review state anywhere else.
- Every command is scoped to the item, pull request or stack it was given; no whole-fork pass runs in a session.
- No session polls or waits: background work runs in an Action and is read on the next call, and a request whose run did not start fails within about 20 seconds.
- v3 lives next to v2 in the same distribution (see basstler-packages), and the pull request that makes a v2 area unnecessary deletes it.
- Every skill has a claude plugin eval with a token and wall-time budget that CI enforces.
- basstler is for anyone: nothing names the owner, a repository or a branch outside configuration.
- An LLM runs only where judgment is needed: in a session through a skill, in an Action through claude-code-action or the Agent SDK. Deterministic work calls the core library directly, never through an LLM or MCP.
- The plugin ships no top-level bin/ and reads no per-user value from userConfig; skills reach basstler through the plugin's .mcp.json server, and per-user configuration stays in personal-notes.env.
