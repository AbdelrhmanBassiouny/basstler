## Plan
- Merge workflow starts the site build on merge: default branch directly; `basstler/plan-site-merge` + auto-opened PR for the user to merge when refused; skipped for forks.

## Done
- `MergeWorkflow` on `pull_request_target`; fallback branch and step; fork skip via GitHub's `fork` flag.
- Actions budget: `pull_request_target`, repository pin as fork guard.
- Merged main (#123, #124); publication's client is `GitHubClient`.
- Review round 1: merge PR opened automatically (reused if open); short module docstring; AGENTS.md docstring-length rule.

## Next
- Docstring thread left open: user to decide on a custom size check (ruff has none).
