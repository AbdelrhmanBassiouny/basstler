## Plan
- Owned REST client behind GitHubClient; callers moved; gh keeps GraphQL + job logs
- cyclopts `basstler` console script for v3 commands

## Done
- basstler.github client + tests (local WSGI stand-in); GitHubRepository, pull-request source, readers, usage, publication, Action-run check moved onto it
- `basstler` command (--version), cyclopts dependency
- Pushed; draft PR #123 description current

## Next
- Owner decision: pin the route in test_a_branch_without_an_upstream_pull_request_exits_without_a_traceback (fails only in cloud sessions)
- CI result on PR #123
