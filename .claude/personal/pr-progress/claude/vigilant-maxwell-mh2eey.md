## Plan
- GitHub API payload keys only inside their models, on pydantic (first slice of payload-key-models).

## Done
- ValidatedJSONModel, Connection, NamedAsGitHub, ConclusionOutcome; pydantic added.
- upstream_reviews GraphQL/REST, release_version, NewPullRequest, RepositoryDetails, WorkflowDispatch, RunListing, RepositoryLabel.
- Full suite at af7cf1d1: 2193 passed, 1 skipped; ruff and code-rules pass.
- Plan: file-key-models, report-key-models, pull-request-record-model added.

## Next
- Owner review of draft PR #158.
