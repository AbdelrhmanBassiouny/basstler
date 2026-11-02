## Plan
- Merge workflow starts the site build on merge: default branch directly; `basstler/plan-site-merge` + auto-opened PR for the user to merge when refused; skipped for forks.

## Done
- `MergeWorkflow` on `pull_request_target`; fallback branch and step; fork skip via GitHub's `fork` flag.
- Actions budget: `pull_request_target`, repository pin as fork guard.
- Merged main (#123, #124); publication's client is `GitHubClient`.
- Review round 1: merge PR opened automatically (reused if open), falling back to the `gh pr create` line with the reason (refusal or no answer); `GitHubWriter.attempt_send`, `GitHubUnreachableError`; short module docstring; AGENTS.md docstring rule.
- Docstring/comment length pre-commit hook split out as draft #126.
- Review round 2: `GitHubCallFailed` base for refusal and no-answer failures (3f67d05).

## Next
- Review on #122.
