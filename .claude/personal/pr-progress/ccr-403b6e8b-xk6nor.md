## Plan
- basstler.github: GitHubReader/GitHubWriter/GitHubClient + urllib GitHubRestClient (page=N, stop on no Link next; token env then `gh auth token`)
- Move GitHubRepository and gh's REST half callers onto it; gh keeps GraphQL + job logs; rename constants.GitHubClient -> GitHubExecutable
- cyclopts `basstler` console script (version), path exported beside BASSTLER_PYTHON

## Done
- Scope settled with owner (no bin/, no userConfig, v3-only command tree); plugin-bin-probe item added
- Draft PR #123 (release:minor)

## Next
- Tests for the REST client against a local HTTP server
