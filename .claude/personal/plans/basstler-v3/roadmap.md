# basstler-v3 — standing rules

- Code does the mechanics and Claude only judges: a skill runs one command that prints a brief of at most 3 KB, decides, and records with one command.
- GitHub is the only store of state; nothing caches plans, stacks, URLs or review state anywhere else.
- Every command is scoped to the item, pull request or stack it was given; no whole-fork pass runs in a session.
- Sessions use git and the GitHub REST API only, never GraphQL, which the cloud proxy refuses.
- No session polls or waits: background work runs in an Action and is read on the next call, and a request whose run did not start fails within about 20 seconds.
- External data is parsed into pydantic dataclasses at the boundary; plain dataclasses everywhere else.
- v3 lives next to v2 in the same package, and the pull request that makes a v2 area unnecessary deletes it.
- Every skill has a claude plugin eval with a token and wall-time budget that CI enforces.
- basstler is for anyone: nothing names the owner, a repository or a branch outside configuration.
- A new dependency, including a development tool, needs the owner's approval first.
