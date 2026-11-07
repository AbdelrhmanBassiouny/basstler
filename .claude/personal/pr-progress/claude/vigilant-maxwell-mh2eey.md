## Plan
- Add pydantic; give JSONModel a validated pydantic subclass with a shared from_json.
- Remove the GitHub API key enums: upstream_reviews (GraphQL, REST), github/pull_request, maintenance (board, github, upstream_action), plan_site (build_start, dispatch_check, publication, run_listing), release_version.
- Tests first for each model; ruff, format hook, code-rules check, full suite.

## Done
- Kickoff: pydantic approved, split into 3 items (file-key-models, report-key-models added), draft PR #158.

## Next
- Validated JSONModel base and its tests.
