# basstler-v3-plans — standing rules

- Code does the mechanics and Claude only judges: a skill runs one command that prints a brief of at most 3 KB, decides, and records with one command.
- GitHub is the only store of state; nothing caches plans, stacks, URLs or review state anywhere else.
- Every command is scoped to the item, pull request or stack it was given; no whole-fork pass runs in a session.
- Sessions use git and the GitHub REST API only, never GraphQL, which the cloud proxy refuses.
- v3 lives next to v2 in the same package, and the pull request that makes a v2 area unnecessary deletes it.
- basstler is for anyone: nothing names the owner, a repository or a branch outside configuration.
- Every new workflow passes actions-budget's rules: no schedule, cancel superseded runs, job timeouts, skip on fork pushes.
- External issues are adopted as sub-issues, never copied: the reporter's issue is the item, and its stage is read from GitHub state.
- An external issue is placed with /add-plan-item before any other stage; the intake only adopts it into the inbox and never decides where it belongs.
