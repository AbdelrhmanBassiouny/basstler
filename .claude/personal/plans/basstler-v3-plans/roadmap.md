# basstler-v3-plans — standing rules

- Code does the mechanics and Claude only judges: a skill runs one command that prints a brief of at most 3 KB, decides, and records with one command.
- GitHub is the only store of stacks, URLs and review state; nothing caches them anywhere else. Plans stay in plan.yaml on the notes branch while plan-store-issues is deferred.
- Every command is scoped to the item, pull request or stack it was given; no whole-fork pass runs in a session.
- Sessions use git and the GitHub REST API only, never GraphQL, which the cloud proxy refuses.
- v3 lives next to v2 in the same package, and the pull request that makes a v2 area unnecessary deletes it.
- basstler is for anyone: nothing names the owner, a repository or a branch outside configuration.
- Every new workflow passes actions-budget's rules: no schedule, cancel superseded runs, job timeouts, skip on fork pushes.
- External issues are adopted as sub-issues, never copied: the reporter's issue is the item, and its stage is read from GitHub state.
- An external issue is placed with /add-plan-item before any other stage; the intake only adopts it into the inbox and never decides where it belongs.
- Split a plan's data by how it changes: its structure (waves, tracks, order, dependencies, item scope) is one YAML block in the tracking issue's body, validated whole and written in one call; each item is a sub-issue carrying only its status, discussion and pull request link.
- Re-read a tracking issue's body before every write, stay under GitHub's 65,536-character body limit, and report a body that does not parse where the user sees it.
- Deleting an item or plan closes its issue as not planned, since REST cannot delete issues; the store reports sub-issues left without a tracking issue.
