## Plan
- Answer the review on #185: one object for live pull request state and read failures; split the site build's test file by module.
- Decide with the user whether a failure that is not about access (401, unreachable, 5xx) should fail the build instead of becoming a warning.

## Done
- 16942d9: `LivePullRequests` replaces the parallel `pull_requests_by_repository` / `read_failures` fields; the GitHub source caches each repository's details answer.
- Tests split into `tests/test_pull_request_source.py`, `tests/plan_site/test_item_classifier.py`, `tests/test_pull_request_state.py`, with `first_plan.py` and `github/pull_request_api.py` shared.
- Merged `main` (0ef3e50).

## Next
- Reply on and resolve the two field threads; leave the file-size thread open on whether to split `plan_site/__main__.py` and `publication.py` in a separate item.
- User's answer on failing the build for a non-access failure.
