**Plan**
- Failing test: a build whose item repository answers 404 renders the page
- GitHubPullRequestSource: read repository details once with attempt_get; unreadable repos are skipped; no try-except
- LiveState.REPOSITORY_UNREADABLE through classify_live_states; not "not found", not drift
- Card note naming the repository and PLAN_SITE_READ_TOKEN; build log warning

**Done**
- Branch, draft PR #185, item recorded in progress

**Next**
- Write the failing tests
