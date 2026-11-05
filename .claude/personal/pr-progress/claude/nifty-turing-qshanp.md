## Plan
- basstler.plan_store: pydantic REST models, ItemBody (scope + Depends on), ItemIssue status, IssuePlanStore over GitHubClient

## Done
- pydantic>=2.11 added (owner-approved), HttpMethod.DELETE, Repository.issue_path, BLOCKED/DEFERRED labels
- Store, body format, status from labels + closing PRs on the timeline; 35 tests
- 8 hand-written endpoint models, 232 lines (58 code), reported in PR #144
- Full suite green apart from 4 environmental Playwright errors; ruff and code-rules pass

## Next
- Owner review of draft PR #144
