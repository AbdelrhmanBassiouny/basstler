## Plan
- Owned REST client behind GitHubClient; callers moved; gh keeps GraphQL + job logs
- cyclopts `basstler` console script for v3 commands

## Done
- Client, callers, `basstler` command, cyclopts dependency
- CI fix: token read at first request; main merged (#124)
- Maintenance test runner hermetic (gh logged out, no CLAUDE_CODE_REMOTE); WSGI review thread resolved

## Next
- CI on 1d3ec73; owner review
