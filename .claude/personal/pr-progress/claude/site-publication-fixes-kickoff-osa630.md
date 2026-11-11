## Plan
- Build `basstler/plan-site-merge` on the default branch's tip; rebuild a copy with no shared history there

## Done
- Failing tests: a fresh branch and a parentless branch from an affected release (1b11cb9)
- Fix in `PlanSitePublication.write_merge_workflow` via `rebuild`, `GitCommandRunner.share_history`, `RemoteBranch.attempt_create` (52698e9)
- Full suite green except 10 browser tests that need a Chromium this environment lacks

## Next
- Review; mark the PR ready
