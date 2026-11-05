## Plan
- Add pydantic>=2 (approved), HttpMethod.DELETE, BLOCKED/DEFERRED labels
- basstler.plan_store: pydantic REST models (issue, label, timeline event)
- Item issue body: scope + "Depends on" references, written and parsed back
- Item status from labels and linked pull request (timeline)
- IssuePlanStore over GitHubClient: create plan, add item (sub-issue), read plan, set/clear blocked/deferred
- Tests first with a recording fake GitHubClient

## Done
- Bootstrap, draft PR #144

## Next
- Tests for the body format and status derivation
