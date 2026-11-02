## Plan
- Owned REST client behind GitHubClient; callers moved; gh keeps GraphQL + job logs
- cyclopts `basstler` console script for v3 commands

## Done
- Client, callers, `basstler` command, cyclopts dependency
- CI fix: token read at first request (3 Action-read tests needed no token)
- main merged (#124); description current

## Next
- Owner decision: hermetic gh in test_a_run_needing_a_credential_it_has_not_got_is_its_own_exit_status (fails only where gh is logged in)
- CI on the new push
