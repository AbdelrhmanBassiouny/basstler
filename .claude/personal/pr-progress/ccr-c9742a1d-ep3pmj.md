## Plan
- Merge workflow starts the site build on merge: default branch directly; `basstler/plan-site-merge` + auto-opened PR for the user to merge when refused; skipped for forks.

## Done
- `MergeWorkflow` on `pull_request_target`; fallback branch and step; fork skip via GitHub's `fork` flag.
- Actions budget: `pull_request_target`, repository pin as fork guard.
- Merged main (#123, #124); publication's client is `GitHubClient`.
- Review round 1: merge PR opened automatically (reused if open), falling back to the `gh pr create` line with GitHub's refusal; `GitHubWriter.attempt_send`; short module docstring; AGENTS.md docstring rule.
- Docstring/comment length pre-commit hook split out as draft #126.

## Next
- Review on #122 (open point: catching network errors needs approval for try-except).
