# basstler-v3-stacks — standing rules

- GitHub is the only store of state; nothing caches plans, stacks, URLs or review state anywhere else.
- Every command is scoped to the item, pull request or stack it was given; no whole-fork pass runs in a session.
- Sessions use git and the GitHub REST API only, never GraphQL, which the cloud proxy refuses.
- No session polls or waits: background work runs in an Action and is read on the next call, and a request whose run did not start fails within about 20 seconds.
- v3 lives next to v2 in the same package, and the pull request that makes a v2 area unnecessary deletes it.
- basstler is for anyone: nothing names the owner, a repository or a branch outside configuration.
- Every new workflow passes actions-budget's rules: no schedule, cancel superseded runs, job timeouts, skip on fork pushes.
- An LLM runs only where judgment is needed: in a session through a skill, in an Action through claude-code-action or the Agent SDK. Deterministic work calls the core library directly, never through an LLM or MCP.
